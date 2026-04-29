"""
AI 트렌드 일일 수집 스크립트

플로우:
1. sources.yaml 로드
2. 각 소스에서 RSS/스크래핑으로 신규 항목 수집
3. 키워드 사전 필터링 (API 호출 절약)
4. Gemini REST API로 카드 구조화
5. data/YYYY/MM/YYYY-MM-DD.json 저장
6. data/seen.json 갱신 (중복 방지)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


# ============================================================
# 설정
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / "scripts" / "sources.yaml"
PROMPT_FILE = REPO_ROOT / "prompts" / "card_generation.md"
DATA_DIR = REPO_ROOT / "data"
SEEN_FILE = DATA_DIR / "seen.json"

# Gemini 모델명 (품질 조정 시 여기서 변경)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ★ 수집 시간 창 (시간 단위). 이 시간보다 오래된 글은 제외.
#   24 = 최근 24시간 (기본, "오늘의 글" 용도)
#   48 = 최근 이틀치 (주말 다음 월요일 등 누락 방지용)
#   72 = 최근 3일치
COLLECTION_WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "168"))

# 키워드 사전 필터 (하나라도 포함되지 않으면 Gemini 호출 생략)
FILTER_KEYWORDS = [
    "model", "release", "launch", "announce", "introduce",
    "update", "version", "feature", "api", "beta",
    "image", "video", "audio", "generate", "generative",
    "ai", "studio", "preview", "available",
]

MAX_ITEMS_PER_SOURCE = 10    # 소스당 검사할 최신 항목 수 (필터 통과 전 기준)
CONTENT_MAX_LENGTH = 2000    # Gemini에 보낼 본문 최대 길이
REQUEST_TIMEOUT = 20         # HTTP 요청 타임아웃 (초)
GEMINI_RATE_LIMIT_SLEEP = 4  # Gemini 호출 간격 (무료 티어 15 RPM 안전 마진)


# ============================================================
# 유틸리티
# ============================================================

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def clean_text(text, max_len=None):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))    # HTML 태그 제거
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def passes_keyword_filter(title, content):
    text = (title + " " + content).lower()
    return any(kw in text for kw in FILTER_KEYWORDS)


def parse_rss_date(entry):
    """RSS entry에서 발행 시각을 UTC datetime으로 파싱"""
    # feedparser가 파싱한 time.struct_time 우선 시도
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    # 문자열에서 직접 파싱 (fallback)
    for field in ("published", "updated", "created"):
        date_str = entry.get(field)
        if date_str:
            try:
                dt = date_parser.parse(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue
    return None


def extract_scrape_date(el):
    """HTML 요소에서 발행 시각 추출 (UTC datetime). 실패 시 None."""
    # 1. <time datetime="..."> 속성 (가장 신뢰도 높음)
    time_el = el.find("time", attrs={"datetime": True})
    if time_el:
        try:
            dt = date_parser.parse(time_el["datetime"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass

    # 2. itemprop="datePublished"
    ip = el.find(attrs={"itemprop": "datePublished"})
    if ip:
        date_str = ip.get("datetime") or ip.get_text(strip=True)
        if date_str:
            try:
                dt = date_parser.parse(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                pass

    # 3. meta 태그 (요소 내부에 있는 경우)
    meta = el.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        try:
            dt = date_parser.parse(meta["content"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass

    return None


# ============================================================
# 수집기
# ============================================================

def collect_rss(source, seen, cutoff):
    """RSS 피드에서 cutoff 이후 발행된 신규 항목만 수집"""
    items = []
    skipped_old = 0
    skipped_no_date = 0
    try:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE * 3]:
            link = entry.get("link", "")
            if not link or link in seen:
                continue

            # 날짜 필터: cutoff보다 오래된 글은 제외
            pub_date = parse_rss_date(entry)
            if pub_date is None:
                skipped_no_date += 1
                seen[link] = datetime.now().isoformat()  # 다음번엔 스킵
                continue
            if pub_date < cutoff:
                skipped_old += 1
                seen[link] = datetime.now().isoformat()
                continue

            content = entry.get("summary", "") or entry.get("description", "")
            items.append({
                "source": source["name"],
                "category": source["category"],
                "title": clean_text(entry.get("title", "")),
                "link": link,
                "content": clean_text(content, CONTENT_MAX_LENGTH),
                "published": pub_date.isoformat(),
            })
            if len(items) >= MAX_ITEMS_PER_SOURCE:
                break

        skipped_summary = []
        if skipped_old:
            skipped_summary.append(f"기간 외 {skipped_old}건")
        if skipped_no_date:
            skipped_summary.append(f"날짜불명 {skipped_no_date}건")
        if skipped_summary:
            print(f"  (제외: {', '.join(skipped_summary)})")
    except Exception as e:
        print(f"  [RSS error] {source['name']}: {e}", file=sys.stderr)
    return items


def collect_scrape(source, seen, cutoff):
    """HTML 페이지에서 selector로 cutoff 이후 글만 수집"""
    items = []
    skipped_old = 0
    skipped_no_date = 0
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AI-Trend-Report/1.0)"
        }
        resp = requests.get(source["url"], headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen_links_this_source = set()
        for el in soup.select(source["selector"])[:MAX_ITEMS_PER_SOURCE * 3]:
            # 링크 추출
            if el.name == "a" and el.get("href"):
                link_el = el
            else:
                link_el = el.find("a", href=True)
            if not link_el:
                continue

            link = urljoin(source["url"], link_el["href"])
            if link in seen or link in seen_links_this_source:
                continue
            seen_links_this_source.add(link)

            # 날짜 필터: 스크래핑은 날짜 확인 불가 시 보수적으로 제외
            pub_date = extract_scrape_date(el)
            if pub_date is None:
                skipped_no_date += 1
                continue  # seen에 기록하지 않음 (다음 수집 때 날짜 붙을 수도)
            if pub_date < cutoff:
                skipped_old += 1
                seen[link] = datetime.now().isoformat()
                continue

            # 제목 추출
            title_el = el.find(["h1", "h2", "h3", "h4"])
            title = clean_text(title_el.get_text() if title_el else link_el.get_text())
            if not title or len(title) < 5:
                continue

            content = clean_text(el.get_text(), CONTENT_MAX_LENGTH)

            items.append({
                "source": source["name"],
                "category": source["category"],
                "title": title,
                "link": link,
                "content": content,
                "published": pub_date.isoformat(),
            })

            if len(items) >= MAX_ITEMS_PER_SOURCE:
                break

        skipped_summary = []
        if skipped_old:
            skipped_summary.append(f"기간 외 {skipped_old}건")
        if skipped_no_date:
            skipped_summary.append(f"날짜불명 {skipped_no_date}건")
        if skipped_summary:
            print(f"  (제외: {', '.join(skipped_summary)})")
    except Exception as e:
        print(f"  [Scrape error] {source['name']}: {e}", file=sys.stderr)
    return items


# ============================================================
# Gemini 분석 (REST API 직접 호출 — SDK 버전 이슈 회피)
# ============================================================

def analyze_with_gemini(api_key, prompt_template, item):
    """기사 → 카드 JSON 변환"""
    user_content = (
        f"[기사 정보]\n"
        f"Source: {item['source']}\n"
        f"Category: {item['category']}\n"
        f"Title: {item['title']}\n"
        f"Content: {item['content']}\n"
    )

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_template + "\n\n" + user_content}]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        analyzed = json.loads(text)

        # 필수 필드 검증
        required = ["model_name", "core_insight", "update_type",
                    "importance", "capability_tags", "application_idea"]
        if not all(k in analyzed for k in required):
            print(f"  [Gemini schema error] Missing fields in: {list(analyzed.keys())}",
                  file=sys.stderr)
            return None

        return analyzed
    except requests.HTTPError as e:
        print(f"  [Gemini HTTP error] {e.response.status_code}: {e.response.text[:200]}",
              file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [Gemini error] {item['title'][:50]}: {e}", file=sys.stderr)
        return None


# ============================================================
# 메인 플로우
# ============================================================

def main():
    print(f"=== Daily AI Trends Collection ===")
    print(f"Started: {datetime.now().isoformat()}\n")

    # 1. 설정 로드
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        print("GitHub Settings → Secrets → Actions 에서 등록 필요.", file=sys.stderr)
        sys.exit(1)

    sources_config = load_yaml(SOURCES_FILE)
    sources = sources_config.get("sources", [])
    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")
    seen = load_json(SEEN_FILE, {})

    # 수집 기간 계산
    cutoff = datetime.now(timezone.utc) - timedelta(hours=COLLECTION_WINDOW_HOURS)
    print(f"설정: 소스 {len(sources)}개, 기존 수집 링크 {len(seen)}개")
    print(f"수집 기간: 최근 {COLLECTION_WINDOW_HOURS}시간 (cutoff: {cutoff.isoformat()})\n")

    # 2. 수집
    all_new_items = []
    for source in sources:
        print(f"[{source['name']}] ({source['type']}) 수집 중...")
        if source["type"] == "rss":
            items = collect_rss(source, seen, cutoff)
        elif source["type"] == "scrape":
            items = collect_scrape(source, seen, cutoff)
        else:
            print(f"  알 수 없는 타입: {source['type']}")
            continue

        # 키워드 사전 필터
        filtered = [i for i in items if passes_keyword_filter(i["title"], i["content"])]
        print(f"  신규 {len(items)}건 → 키워드 필터 통과 {len(filtered)}건")

        all_new_items.extend(filtered)
        # seen 갱신 (Gemini 분석 성공 여부와 무관하게 기록 → 중복 방지)
        for i in items:
            seen[i["link"]] = datetime.now().isoformat()

    if not all_new_items:
        print("\n수집된 신규 항목이 없습니다. 종료.")
        save_json(SEEN_FILE, seen)
        # 빈 일일 파일도 생성 (빌드 시 "업데이트 없음" 페이지용)
        today = datetime.now().strftime("%Y-%m-%d")
        out_path = DATA_DIR / today[:4] / today[5:7] / f"{today}.json"
        if not out_path.exists():
            save_json(out_path, [])
        return

    print(f"\n=== Gemini 분석 시작 ({len(all_new_items)}건) ===\n")

    # 3. Gemini 분석
    cards = []
    for idx, item in enumerate(all_new_items, 1):
        print(f"[{idx}/{len(all_new_items)}] {item['source']}")
        print(f"  → {item['title'][:70]}")

        analyzed = analyze_with_gemini(api_key, prompt_template, item)
        if analyzed is None:
            print(f"  (분석 실패, 건너뜀)\n")
            continue

        cards.append({
            **analyzed,
            "source": item["source"],
            "category": item["category"],
            "link": item["link"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "original_title": item["title"],
        })
        print(f"  ✓ {analyzed.get('importance')} / {analyzed.get('update_type')}"
              f" / {analyzed.get('model_name')}\n")

        # Rate limit 준수 (무료 티어 15 RPM)
        time.sleep(GEMINI_RATE_LIMIT_SLEEP)

    # 4. 저장
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = DATA_DIR / today[:4] / today[5:7] / f"{today}.json"
    save_json(out_path, cards)
    save_json(SEEN_FILE, seen)

    print(f"=== 완료 ===")
    print(f"✓ {len(cards)}개 카드 저장: {out_path.relative_to(REPO_ROOT)}")
    print(f"✓ seen.json 업데이트: 총 {len(seen)}개 링크 기록됨")


if __name__ == "__main__":
    main()
