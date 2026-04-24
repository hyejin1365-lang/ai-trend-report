"""
주간 / 월간 / 분기 합성 리포트 생성 스크립트

플로우:
1. 명령줄 인자로 모드 선택 (weekly | monthly | quarterly)
2. 해당 기간의 일일 카드를 모두 로드
3. Gemini로 합성 (트렌드 클러스터링 + 실무 권고)
4. 결과를 JSON으로 저장 (data/{kind}/{period_id}.json)

데이터가 충분하지 않으면 'data_insufficient' 플래그가 설정된 리포트가 생성됨.
build.py가 이 플래그를 보고 "데이터 부족" 안내를 페이지에 표시.

호출 방법 (workflow에서):
    python scripts/reports.py weekly      # 매주 일요일 자동
    python scripts/reports.py monthly     # 매월 말일 자동
    python scripts/reports.py quarterly   # 매분기 말일 자동
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# 데이터 충분성 기준 (이 미만이면 data_insufficient 플래그 설정)
MIN_CARDS = {
    "weekly": 10,
    "monthly": 40,
    "quarterly": 120,
}

# 기간 길이 (일 단위)
PERIOD_DAYS = {
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
}


# ============================================================
# 유틸리티
# ============================================================

def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def collect_daily_cards(start_date, end_date):
    """[start_date, end_date] 범위의 일일 카드를 모두 수집"""
    cards = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        path = DATA_DIR / date_str[:4] / date_str[5:7] / f"{date_str}.json"
        day_cards = load_json(path, [])
        cards.extend(day_cards)
        current += timedelta(days=1)
    return cards


# ============================================================
# 기간 식별자
# ============================================================

def get_weekly_period():
    """이번 주(월~일) 범위 반환. 일요일 실행 가정."""
    today = datetime.now(timezone.utc).date()
    # 가장 최근 월요일 찾기
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_week, _ = today.isocalendar()
    period_id = f"{iso_year}-W{iso_week:02d}"
    return monday, sunday, period_id


def get_monthly_period():
    """지난 달(1일~말일) 범위. 매월 1일 실행 가정."""
    today = datetime.now(timezone.utc).date()
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    period_id = f"{first_of_prev.year}-{first_of_prev.month:02d}"
    return first_of_prev, last_of_prev, period_id


def get_quarterly_period():
    """지난 분기 범위. 분기 첫 달 1일 실행 가정 (1/1, 4/1, 7/1, 10/1)."""
    today = datetime.now(timezone.utc).date()
    current_q = (today.month - 1) // 3 + 1
    if current_q == 1:
        prev_q_year = today.year - 1
        prev_q = 4
    else:
        prev_q_year = today.year
        prev_q = current_q - 1
    start_month = (prev_q - 1) * 3 + 1
    end_month = start_month + 2
    start_date = datetime(prev_q_year, start_month, 1).date()
    if end_month == 12:
        end_date = datetime(prev_q_year, 12, 31).date()
    else:
        end_date = datetime(prev_q_year, end_month + 1, 1).date() - timedelta(days=1)
    period_id = f"{prev_q_year}-Q{prev_q}"
    return start_date, end_date, period_id


# ============================================================
# Gemini 합성 호출
# ============================================================

def build_prompt(kind, cards, start_date, end_date):
    """모드별 합성 프롬프트 생성"""
    cards_summary = "\n".join(
        f"- [{c.get('date','')}] [{c.get('importance','참고')}] "
        f"{c.get('source','')} · {c.get('model_name','')} — {c.get('core_insight','')}"
        for c in cards
    )

    base_context = f"""당신은 한국 공간 콘텐츠 제작팀(전시·미디어아트·프로젝션 매핑·VR/AR/XR)의 AI 트렌드 분석가입니다.
주력 도구: Adobe Photoshop, AfterEffects, Premiere, Unreal Engine, TouchDesigner.

기간: {start_date} ~ {end_date}
수집된 카드 수: {len(cards)}건

[수집 카드 요약]
{cards_summary}
"""

    if kind == "weekly":
        instruction = """
이 주간 데이터를 분석해 다음 JSON 구조로 응답하세요. JSON만 출력 (마크다운 코드블록 없이).

{
  "period_id": "2026-W17 형식",
  "period_label": "사람이 읽기 좋은 라벨 (예: '4월 셋째 주')",
  "summary_one_liner": "이번 주를 한 줄로 요약 (40자 이내)",
  "trends": [
    {
      "title": "트렌드 제목 (15자 이내)",
      "description": "이 트렌드의 의미와 패턴을 2-3문장으로 (단일 카드가 아닌 여러 카드를 묶어 추출한 흐름)",
      "related_models": ["관련 모델 목록"],
      "team_implication": "공간 콘텐츠 팀 관점의 시사점 1-2문장"
    }
  ],
  "top_picks": [
    {"model_name": "이번 주 가장 주목할 모델", "reason": "왜 주목해야 하는지 1문장"}
  ]
}

규칙:
- trends는 2~4개 (강제로 만들지 말 것 — 데이터가 적으면 1개도 OK)
- top_picks는 1~3개
- 단일 카드 정보의 반복이 아니라 패턴·흐름 추출
- 톤: 내부 팀 공유용. 간결하고 실무적.
"""
    elif kind == "monthly":
        instruction = """
이 월간 데이터를 분석해 다음 JSON 구조로 응답하세요. JSON만 출력.

{
  "period_id": "2026-04 형식",
  "period_label": "2026년 4월",
  "summary_one_liner": "이번 달을 한 줄로 요약 (50자 이내)",
  "monthly_trajectory": "이번 달 트렌드의 궤적 분석 3-4문장 (어떤 방향으로 흐르고 있는지, 가속/감속/전환 구간)",
  "trends": [
    {
      "title": "월간 핵심 트렌드 (15자 이내)",
      "description": "이번 달에 형성·강화·전환된 흐름 3-4문장",
      "related_models": ["관련 모델 목록"],
      "team_implication": "공간 콘텐츠 팀이 다음 달 무엇을 준비해야 하는지 2-3문장"
    }
  ],
  "platform_activity": [
    {"platform": "OpenAI", "card_count": 8, "key_releases": ["주요 릴리스 1-3개"]}
  ]
}

규칙:
- trends는 2~3개의 굵직한 흐름만
- 톤: 리더 공유용. 방향성과 시사점 중심.
"""
    else:  # quarterly
        instruction = """
이 분기 데이터를 분석해 다음 JSON 구조로 응답하세요. JSON만 출력.

{
  "period_id": "2026-Q2 형식",
  "period_label": "2026년 2분기",
  "executive_summary": [
    "경영진을 위한 3줄 요약 (각 줄 60자 이내, 의사결정 가능한 수준의 인사이트)",
    "두 번째 줄",
    "세 번째 줄"
  ],
  "trends": [
    {
      "title": "분기 핵심 트렌드 (15자 이내)",
      "description": "이번 분기에 일어난 구조적 변화 4-5문장",
      "related_models": ["관련 모델"],
      "trajectory": "이 트렌드의 향후 6개월 전망 1-2문장"
    }
  ],
  "platform_activity": [
    {"platform": "OpenAI", "card_count": 24, "share_pct": 18}
  ],
  "recommendations": {
    "immediate": "즉시 도입 권고 1-2개 (구체적 모델명 + 시범 적용 시나리오)",
    "pipeline_review": "파이프라인·프로세스 검토 권고 1-2개",
    "watch": "다음 분기 재평가 대상 1-2개"
  }
}

규칙:
- 톤: 외부용 / 경영진 보고용. 정중하고 단정한 한국어.
- recommendations는 막연한 표현 금지. "검토 필요" 같은 빈 말 대신 구체적 액션.
- 인용은 모델명·플랫폼명 정확하게.
"""

    return base_context + instruction


def call_gemini(api_key, prompt):
    """Gemini REST API 호출, JSON 응답 파싱"""
    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.4,
        }
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


# ============================================================
# 메인 플로우
# ============================================================

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("weekly", "monthly", "quarterly"):
        print("Usage: python scripts/reports.py [weekly|monthly|quarterly]", file=sys.stderr)
        sys.exit(1)

    kind = sys.argv[1]
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY 미설정", file=sys.stderr)
        sys.exit(1)

    # 1. 기간 결정
    if kind == "weekly":
        start_date, end_date, period_id = get_weekly_period()
    elif kind == "monthly":
        start_date, end_date, period_id = get_monthly_period()
    else:
        start_date, end_date, period_id = get_quarterly_period()

    print(f"=== {kind.upper()} report 생성 ===")
    print(f"기간: {start_date} ~ {end_date} (id: {period_id})\n")

    # 2. 일일 카드 수집
    cards = collect_daily_cards(start_date, end_date)
    print(f"수집된 카드: {len(cards)}건")

    # 3. 데이터 충분성 체크
    min_required = MIN_CARDS[kind]
    data_insufficient = len(cards) < min_required

    if len(cards) == 0:
        print("카드가 0건. 빈 리포트 저장 후 종료.")
        report = {
            "kind": kind,
            "period_id": period_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "card_count": 0,
            "data_insufficient": True,
            "data_insufficient_reason": "수집된 카드 없음",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        # 4. Gemini 호출
        prompt = build_prompt(kind, cards, start_date, end_date)
        print(f"Gemini 호출 (토큰 약 {len(prompt)//4}개)...")
        try:
            synthesis = call_gemini(api_key, prompt)
            print(f"✓ 합성 성공: {synthesis.get('summary_one_liner', synthesis.get('executive_summary', ['']))[:60]}...")
        except Exception as e:
            print(f"✗ Gemini 합성 실패: {e}", file=sys.stderr)
            synthesis = {"_error": str(e)}

        report = {
            "kind": kind,
            "period_id": period_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "card_count": len(cards),
            "data_insufficient": data_insufficient,
            "data_insufficient_reason": (
                f"데이터 누적 부족 (수집 {len(cards)}건 / 정상 기준 {min_required}건+)"
                if data_insufficient else None
            ),
            "synthesis": synthesis,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # 5. 저장
    out_path = DATA_DIR / kind / f"{period_id}.json"
    save_json(out_path, report)
    print(f"\n✓ 저장: {out_path.relative_to(REPO_ROOT)}")

    if data_insufficient:
        print(f"⚠ 데이터 부족 플래그 설정됨 (페이지에 안내 표시됨)")


if __name__ == "__main__":
    main()
