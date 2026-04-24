"""
정적 사이트 빌더
data/*.json → docs/index.html

오늘 + 최근 6일치 일일 JSON을 읽어 일자별 섹션으로 렌더링.
"""

import html
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"

DISPLAY_DAYS = 7  # 메인 페이지에 보여줄 최근 일수


def load_recent_days(days=DISPLAY_DAYS):
    """최근 N일치 일일 JSON을 일자별로 묶어 반환. {date_str: [cards]}"""
    if not DATA_DIR.exists():
        return {}
    by_date = {}
    for f in DATA_DIR.rglob("*.json"):
        if f.name == "seen.json":
            continue
        if "weekly" in str(f) or "monthly" in str(f) or "quarterly" in str(f):
            continue
        try:
            datetime.strptime(f.stem, "%Y-%m-%d")
        except ValueError:
            continue
        try:
            cards = json.loads(f.read_text(encoding="utf-8"))
            if cards:
                by_date[f.stem] = cards
        except json.JSONDecodeError:
            continue

    # 최근 N일만 (최신순 정렬)
    sorted_dates = sorted(by_date.keys(), reverse=True)[:days]
    return {d: by_date[d] for d in sorted_dates}


def find_latest_daily_json():
    """(하위 호환용) 가장 최근 일일 JSON"""
    recent = load_recent_days(days=1)
    if not recent:
        return None, None
    date_str = next(iter(recent))
    return recent[date_str], date_str


def format_date_ko(date_str):
    """2026-04-24 → 2026.04.24 (금)"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = "월화수목금토일"[dt.weekday()]
        return f"{dt.strftime('%Y.%m.%d')} ({weekday})"
    except ValueError:
        return date_str


def esc(s):
    return html.escape(str(s or ""))


def render_hero_card(card):
    importance = card.get("importance", "참고")
    color = {"핵심": "#E24B4A", "주목": "#EF9F27", "참고": "#B4B2A9"}.get(importance, "#B4B2A9")

    tags_html = " ".join(
        f'<span class="tag">#{esc(t)}</span>'
        for t in card.get("capability_tags", [])
    )

    return f"""
<article class="card card--hero" style="border-left-color: {color};">
  <div class="card__meta">
    <span class="badge badge--type">{esc(card.get('update_type', ''))}</span>
    <span class="badge badge--category">{esc(card.get('category', ''))}</span>
    <span class="card__source">{esc(card.get('source', ''))} · {esc(card.get('date', ''))}</span>
  </div>
  <h3 class="card__model">{esc(card.get('model_name', ''))}</h3>
  <div class="card__insight-block">
    <div class="card__label">핵심 인사이트</div>
    <a href="{esc(card.get('link', '#'))}" class="card__insight" target="_blank" rel="noopener">{esc(card.get('core_insight', ''))} ↗</a>
  </div>
  <div class="card__application">
    <div class="card__label card__label--on-color">공간 콘텐츠 활용 아이디어</div>
    <p>{esc(card.get('application_idea', ''))}</p>
  </div>
  <div class="card__tags">{tags_html}</div>
</article>
"""


def render_mini_card(card):
    importance = card.get("importance", "참고")
    color = {"핵심": "#E24B4A", "주목": "#EF9F27", "참고": "#B4B2A9"}.get(importance, "#B4B2A9")

    return f"""
<article class="card card--mini" style="border-left-color: {color};">
  <div class="card__meta card__meta--mini">
    <span class="badge badge--mini">{esc(card.get('update_type', ''))}</span>
    <span class="card__source">{esc(card.get('category', ''))}</span>
  </div>
  <h4 class="card__model card__model--mini">{esc(card.get('model_name', ''))}</h4>
  <a href="{esc(card.get('link', '#'))}" class="card__insight card__insight--mini" target="_blank" rel="noopener">{esc(card.get('core_insight', ''))}</a>
</article>
"""


def render_empty_page(date_display):
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 트렌드 일일 리포트</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", sans-serif;
  color: #2C2C2A; background: #F7F6F2;
  padding: 80px 20px; text-align: center; line-height: 1.7;
}}
h1 {{ font-size: 22px; font-weight: 500; margin-bottom: 8px; }}
p {{ color: #5F5E5A; font-size: 14px; }}
.date {{ font-size: 12px; color: #888780; margin-bottom: 24px; letter-spacing: 1px; text-transform: uppercase; }}
@media (prefers-color-scheme: dark) {{
  body {{ color: #D3D1C7; background: #1a1a1a; }}
  p {{ color: #B4B2A9; }}
}}
</style>
</head>
<body>
<div class="date">{esc(date_display)}</div>
<h1>오늘은 신규 업데이트가 없습니다</h1>
<p>수집 대상 플랫폼에서 신규 공지가 감지되지 않았어요.<br>내일 09:00에 다시 수집됩니다.</p>
</body>
</html>
"""


def render_day_section(date_str, cards):
    """한 일자의 카드들을 핵심+그 외 섹션으로 렌더링"""
    importance_order = {"핵심": 0, "주목": 1, "참고": 2}
    cards.sort(key=lambda c: importance_order.get(c.get("importance", "참고"), 3))

    hero_cards = [c for c in cards if c.get("importance") == "핵심"]
    other_cards = [c for c in cards if c.get("importance") != "핵심"]

    parts = [f'<section class="day-section">']
    parts.append(f'<h2 class="day-title">{esc(format_date_ko(date_str))} <span class="day-count">· 총 {len(cards)}건</span></h2>')

    if hero_cards:
        parts.append(f'<div class="day-subsection-label">핵심 · {len(hero_cards)}건</div>')
        parts.extend(render_hero_card(c) for c in hero_cards)

    if other_cards:
        parts.append(f'<div class="day-subsection-label">그 외 · {len(other_cards)}건 (핵심 제외)</div>')
        parts.append('<div class="grid">')
        parts.extend(render_mini_card(c) for c in other_cards)
        parts.append('</div>')

    parts.append('</section>')
    return "\n".join(parts)


def render_page(by_date):
    """by_date: {date_str: [cards]}, 최신 일자가 먼저 오도록 이미 정렬된 dict"""
    if not by_date:
        return render_empty_page("수집 대기 중")

    sorted_dates = sorted(by_date.keys(), reverse=True)
    latest_date = sorted_dates[0]
    total_cards = sum(len(v) for v in by_date.values())

    sections_html = "\n".join(render_day_section(d, by_date[d]) for d in sorted_dates)

    return PAGE_TEMPLATE.format(
        date_display=esc(format_date_ko(latest_date)),
        total_count=total_cards,
        days_count=len(sorted_dates),
        sections=sections_html,
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 트렌드 일일 리포트 · {date_display}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", sans-serif;
  color: #2C2C2A;
  background: #F7F6F2;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 60px; }}

header {{ margin-bottom: 16px; display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 8px; }}
.head-left .tag-line {{
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #888780; margin-bottom: 6px; font-weight: 500;
}}
.head-left h1 {{ font-size: 26px; font-weight: 500; margin-bottom: 4px; color: #2C2C2A; }}
.head-left .sub {{ font-size: 13px; color: #5F5E5A; }}
.head-date {{ font-size: 13px; color: #5F5E5A; }}

.section-title {{
  font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase;
  color: #5F5E5A; margin: 36px 0 14px; font-weight: 500;
}}

.card {{
  background: #FFFFFF;
  border: 0.5px solid rgba(0,0,0,0.1);
  border-left: 3px solid #B4B2A9;
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 14px;
}}
.card--hero {{ padding: 22px 26px; }}
.card--mini {{ padding: 15px 18px; margin-bottom: 0; }}

.card__meta {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
.card__meta--mini {{ margin-bottom: 8px; justify-content: space-between; }}

.badge {{
  font-size: 11px; padding: 3px 8px; border-radius: 4px;
  background: #E6F1FB; color: #042C53; font-weight: 500;
}}
.badge--category {{ background: #F1EFE8; color: #444441; }}
.badge--mini {{ font-size: 10px; padding: 2px 6px; }}

.card__source {{ font-size: 11px; color: #B4B2A9; margin-left: auto; }}
.card--mini .card__source {{ margin-left: 0; }}

.card__model {{ font-size: 19px; font-weight: 500; margin-bottom: 14px; color: #2C2C2A; }}
.card__model--mini {{ font-size: 14px; margin-bottom: 6px; }}

.card__insight-block {{
  padding: 12px 0;
  border-top: 0.5px solid rgba(0,0,0,0.08);
  border-bottom: 0.5px solid rgba(0,0,0,0.08);
  margin-bottom: 14px;
}}

.card__label {{
  font-size: 11px; color: #5F5E5A; margin-bottom: 6px; font-weight: 500;
}}
.card__label--on-color {{ color: #04342C; }}

.card__insight {{
  font-size: 14px; color: #2C2C2A; text-decoration: none; line-height: 1.55; display: block;
}}
.card__insight:hover {{ color: #185FA5; }}
.card__insight--mini {{ font-size: 12px; color: #5F5E5A; }}
.card__insight--mini:hover {{ color: #185FA5; }}

.card__application {{
  background: #E1F5EE; padding: 14px 16px; border-radius: 6px; margin-bottom: 12px;
}}
.card__application p {{ font-size: 14px; line-height: 1.65; color: #04342C; }}

.card__tags {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.tag {{ font-size: 11px; color: #B4B2A9; }}

.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}}

.empty-note {{ color: #888780; font-size: 13px; padding: 16px 0; }}

.footer-nav {{
  margin-top: 40px; padding-top: 20px;
  border-top: 0.5px solid rgba(0,0,0,0.1);
  display: flex; gap: 16px; font-size: 13px;
  color: #5F5E5A;
}}
.footer-nav a {{ color: #185FA5; text-decoration: none; }}
.footer-nav a:hover {{ text-decoration: underline; }}

@media (prefers-color-scheme: dark) {{
  body {{ color: #D3D1C7; background: #1a1a1a; }}
  .head-left h1 {{ color: #D3D1C7; }}
  .day-title {{ color: #D3D1C7; }}
  .card {{ background: #252524; border-color: rgba(255,255,255,0.08); }}
  .card__model {{ color: #D3D1C7; }}
  .card__insight {{ color: #D3D1C7; }}
  .card__insight:hover, .card__insight--mini:hover {{ color: #85B7EB; }}
  .card__insight-block {{ border-color: rgba(255,255,255,0.08); }}
  .badge {{ background: #0C447C; color: #E6F1FB; }}
  .badge--category {{ background: #444441; color: #D3D1C7; }}
  .card__application {{ background: #085041; }}
  .card__application p {{ color: #9FE1CB; }}
  .card__label--on-color {{ color: #9FE1CB; }}
  .footer-nav a {{ color: #85B7EB; }}
}}

.day-section {{
  margin-top: 36px;
  padding-top: 24px;
  border-top: 0.5px solid rgba(0,0,0,0.1);
}}
.day-section:first-of-type {{ margin-top: 24px; padding-top: 0; border-top: none; }}
.day-title {{
  font-size: 18px; font-weight: 500; color: #2C2C2A;
  margin-bottom: 14px;
}}
.day-count {{ font-size: 13px; color: #888780; font-weight: 400; }}
.day-subsection-label {{
  font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase;
  color: #888780; margin: 18px 0 10px; font-weight: 500;
}}

@media (max-width: 600px) {{
  .head-left h1 {{ font-size: 22px; }}
  .card--hero {{ padding: 18px 20px; }}
  .card__model {{ font-size: 17px; }}
}}
</style>
</head>
<body>
<div class="container">

<header>
  <div class="head-left">
    <div class="tag-line">AI 트렌드 일일 리포트</div>
    <h1>최근 업데이트</h1>
    <div class="sub">공간 콘텐츠 제작 기술 트렌드 · 최근 {days_count}일 · 총 {total_count}건</div>
  </div>
  <div class="head-date">{date_display}</div>
</header>

{sections}

<div class="footer-nav">
  <span>누적 리포트</span>
  <a href="weekly.html">주간 →</a>
  <a href="monthly.html">월간 →</a>
  <a href="quarterly.html">분기 →</a>
</div>

</div>
</body>
</html>
"""


def render_report_page(report, kind):
    """주간/월간/분기 리포트 페이지 HTML 생성"""
    if not report:
        return _empty_report_page(kind)

    period_label = report.get("synthesis", {}).get("period_label") or report.get("period_id", "")
    start_date = report.get("start_date", "")
    end_date = report.get("end_date", "")
    card_count = report.get("card_count", 0)
    insufficient = report.get("data_insufficient", False)
    insufficient_reason = report.get("data_insufficient_reason", "")
    synthesis = report.get("synthesis", {}) or {}

    kind_label = {"weekly": "주간 리포트", "monthly": "월간 리포트", "quarterly": "분기 리포트"}[kind]

    parts = [_REPORT_PAGE_HEAD.format(
        kind_label=esc(kind_label),
        title_suffix=esc(period_label or report.get("period_id", "")),
    )]

    # 헤더
    parts.append(f'''<header class="rpt-header">
      <div class="rpt-tag">{esc(kind_label)} · {esc(report.get("period_id", ""))}</div>
      <h1 class="rpt-title">{esc(period_label or "AI 트렌드 리포트")}</h1>
      <div class="rpt-sub">{esc(start_date)} — {esc(end_date)} · 수집 {card_count}건</div>
    </header>''')

    # 데이터 부족 안내
    if insufficient:
        parts.append(f'''<div class="rpt-warning">
          <div class="rpt-warning-label">⚠ 데이터 부족 안내</div>
          <p>{esc(insufficient_reason or "")}<br>충분한 데이터가 누적되면 자동으로 정상 리포트가 생성됩니다.</p>
        </div>''')

    # 한 줄 요약 (주간/월간)
    one_liner = synthesis.get("summary_one_liner")
    if one_liner:
        parts.append(f'<div class="rpt-oneliner">{esc(one_liner)}</div>')

    # Executive Summary (분기 전용)
    exec_summary = synthesis.get("executive_summary")
    if exec_summary and isinstance(exec_summary, list):
        parts.append('<section class="rpt-section">')
        parts.append('<div class="rpt-section-label">Executive Summary</div>')
        parts.append('<ol class="rpt-exec-list">')
        for line in exec_summary:
            parts.append(f'<li>{esc(line)}</li>')
        parts.append('</ol></section>')

    # 월간 궤적
    trajectory = synthesis.get("monthly_trajectory")
    if trajectory:
        parts.append(f'''<section class="rpt-section">
          <div class="rpt-section-label">이번 달 궤적</div>
          <p class="rpt-trajectory">{esc(trajectory)}</p>
        </section>''')

    # 트렌드 카드
    trends = synthesis.get("trends") or []
    if trends:
        parts.append('<section class="rpt-section">')
        parts.append(f'<div class="rpt-section-label">주요 트렌드 · {len(trends)}건</div>')
        parts.append('<div class="rpt-trends">')
        for i, t in enumerate(trends, 1):
            related = t.get("related_models") or []
            related_html = " ".join(f'<span class="rpt-tag-small">{esc(m)}</span>' for m in related)
            implication_field = t.get("team_implication") or t.get("trajectory") or ""
            parts.append(f'''<div class="rpt-trend">
              <div class="rpt-trend-num">TREND {i:02d}</div>
              <div class="rpt-trend-title">{esc(t.get("title", ""))}</div>
              <p class="rpt-trend-desc">{esc(t.get("description", ""))}</p>
              {f'<div class="rpt-tags">{related_html}</div>' if related else ''}
              {f'<div class="rpt-implication"><strong>시사점</strong> · {esc(implication_field)}</div>' if implication_field else ''}
            </div>''')
        parts.append('</div></section>')

    # Top picks (주간 전용)
    top_picks = synthesis.get("top_picks") or []
    if top_picks:
        parts.append('<section class="rpt-section">')
        parts.append('<div class="rpt-section-label">이번 주 주목할 모델</div>')
        parts.append('<ul class="rpt-picks">')
        for p in top_picks:
            parts.append(
                f'<li><strong>{esc(p.get("model_name",""))}</strong> — '
                f'{esc(p.get("reason",""))}</li>'
            )
        parts.append('</ul></section>')

    # 플랫폼 활성도 (월간/분기)
    platform = synthesis.get("platform_activity") or []
    if platform:
        max_count = max((p.get("card_count", 0) for p in platform), default=1) or 1
        parts.append('<section class="rpt-section">')
        parts.append('<div class="rpt-section-label">플랫폼별 업데이트 활성도</div>')
        parts.append('<div class="rpt-bars">')
        for p in platform:
            cnt = p.get("card_count", 0)
            pct = int((cnt / max_count) * 100) if max_count else 0
            parts.append(f'''<div class="rpt-bar-row">
              <div class="rpt-bar-label">{esc(p.get("platform", ""))}</div>
              <div class="rpt-bar-track"><div class="rpt-bar-fill" style="width: {pct}%;"></div></div>
              <div class="rpt-bar-value">{cnt}</div>
            </div>''')
        parts.append('</div></section>')

    # 권고 (분기 전용)
    rec = synthesis.get("recommendations")
    if rec and isinstance(rec, dict):
        parts.append('<section class="rpt-section">')
        parts.append('<div class="rpt-section-label">실무 도입 권고</div>')
        parts.append('<div class="rpt-rec-block">')
        for label, key in [("① 우선 도입", "immediate"), ("② 파이프라인 검토", "pipeline_review"), ("③ 관망", "watch")]:
            text = rec.get(key, "")
            if text:
                parts.append(f'''<div class="rpt-rec">
                  <div class="rpt-rec-label">{esc(label)}</div>
                  <p>{esc(text)}</p>
                </div>''')
        parts.append('</div></section>')

    # 푸터 메타데이터
    parts.append(f'''<footer class="rpt-footer">
      <span>수집 {card_count}건 · 기간 {start_date} ~ {end_date}</span>
      <span>Gemini 2.5 Flash · {esc(report.get("generated_at", "")[:10])}</span>
    </footer>''')

    parts.append('<div class="rpt-nav"><a href="index.html">← 일일 리포트로</a></div>')
    parts.append('</div></body></html>')

    return "\n".join(parts)


def _empty_report_page(kind):
    label = {"weekly": "주간 리포트", "monthly": "월간 리포트", "quarterly": "분기 리포트"}[kind]
    return _REPORT_PAGE_HEAD.format(kind_label=esc(label), title_suffix="준비 중") + f'''
    <header class="rpt-header">
      <div class="rpt-tag">{label}</div>
      <h1 class="rpt-title">아직 생성된 리포트가 없습니다</h1>
      <div class="rpt-sub">충분한 일일 데이터가 누적되면 자동 생성됩니다.</div>
    </header>
    <div class="rpt-nav"><a href="index.html">← 일일 리포트로</a></div>
    </div></body></html>'''


_REPORT_PAGE_HEAD = '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{kind_label} · {title_suffix}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", sans-serif;
  color: #2C2C2A; background: #F7F6F2; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 800px; margin: 0 auto; padding: 40px 20px 60px; background: #FFFFFF; border-radius: 8px; }}
@media (max-width: 700px) {{ .container {{ padding: 28px 18px; }} }}
.rpt-header {{ padding-bottom: 24px; border-bottom: 0.5px solid rgba(0,0,0,0.1); margin-bottom: 28px; }}
.rpt-tag {{ font-size: 11px; color: #888780; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 8px; font-weight: 500; }}
.rpt-title {{ font-size: 26px; font-weight: 500; margin-bottom: 6px; color: #2C2C2A; }}
.rpt-sub {{ font-size: 13px; color: #5F5E5A; }}
.rpt-warning {{ background: #FAEEDA; border-left: 3px solid #BA7517; padding: 16px 20px; border-radius: 6px; margin-bottom: 24px; }}
.rpt-warning-label {{ font-size: 11px; color: #854F0B; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 8px; font-weight: 500; }}
.rpt-warning p {{ font-size: 13px; color: #854F0B; line-height: 1.6; }}
.rpt-oneliner {{ font-size: 18px; font-weight: 500; color: #2C2C2A; padding: 18px 0; margin-bottom: 12px; line-height: 1.5; }}
.rpt-section {{ margin-top: 32px; }}
.rpt-section-label {{ font-size: 11px; color: #5F5E5A; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 14px; font-weight: 500; }}
.rpt-exec-list {{ padding-left: 22px; font-size: 14px; line-height: 1.85; }}
.rpt-exec-list li {{ margin-bottom: 8px; }}
.rpt-trajectory {{ font-size: 14px; line-height: 1.7; color: #444441; }}
.rpt-trends {{ display: flex; flex-direction: column; gap: 14px; }}
.rpt-trend {{ border: 0.5px solid rgba(0,0,0,0.1); border-radius: 8px; padding: 18px 20px; background: #FAFAF7; }}
.rpt-trend-num {{ font-size: 10px; color: #185FA5; font-weight: 500; letter-spacing: 0.6px; margin-bottom: 8px; }}
.rpt-trend-title {{ font-size: 16px; font-weight: 500; margin-bottom: 8px; color: #2C2C2A; }}
.rpt-trend-desc {{ font-size: 13px; line-height: 1.65; color: #444441; margin-bottom: 10px; }}
.rpt-tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }}
.rpt-tag-small {{ font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #F1EFE8; color: #444441; }}
.rpt-implication {{ font-size: 13px; line-height: 1.6; color: #04342C; background: #E1F5EE; padding: 10px 14px; border-radius: 6px; }}
.rpt-implication strong {{ font-weight: 500; }}
.rpt-picks {{ list-style: none; padding: 0; }}
.rpt-picks li {{ font-size: 14px; padding: 10px 0; border-bottom: 0.5px solid rgba(0,0,0,0.06); line-height: 1.6; }}
.rpt-picks li:last-child {{ border-bottom: none; }}
.rpt-picks li strong {{ font-weight: 500; color: #2C2C2A; }}
.rpt-bars {{ display: flex; flex-direction: column; gap: 10px; }}
.rpt-bar-row {{ display: grid; grid-template-columns: 110px 1fr 36px; gap: 14px; align-items: center; font-size: 13px; }}
.rpt-bar-label {{ color: #444441; }}
.rpt-bar-track {{ height: 10px; background: #F1EFE8; border-radius: 4px; }}
.rpt-bar-fill {{ height: 100%; background: #2C2C2A; border-radius: 4px; }}
.rpt-bar-value {{ color: #5F5E5A; text-align: right; font-variant-numeric: tabular-nums; }}
.rpt-rec-block {{ background: #E6F1FB; padding: 20px 22px; border-radius: 8px; }}
.rpt-rec {{ margin-bottom: 14px; }}
.rpt-rec:last-child {{ margin-bottom: 0; }}
.rpt-rec-label {{ font-size: 12px; color: #042C53; font-weight: 500; margin-bottom: 4px; }}
.rpt-rec p {{ font-size: 14px; color: #042C53; line-height: 1.55; }}
.rpt-footer {{ margin-top: 36px; padding-top: 18px; border-top: 0.5px solid rgba(0,0,0,0.1); display: flex; justify-content: space-between; font-size: 11px; color: #888780; }}
.rpt-nav {{ margin-top: 24px; font-size: 13px; }}
.rpt-nav a {{ color: #185FA5; text-decoration: none; }}
.rpt-nav a:hover {{ text-decoration: underline; }}
@media (prefers-color-scheme: dark) {{
  body {{ color: #D3D1C7; background: #1a1a1a; }}
  .container {{ background: #252524; }}
  .rpt-title, .rpt-trend-title, .rpt-oneliner, .rpt-picks li strong {{ color: #D3D1C7; }}
  .rpt-trend {{ background: #1a1a1a; border-color: rgba(255,255,255,0.08); }}
  .rpt-trend-desc, .rpt-trajectory, .rpt-bar-label {{ color: #D3D1C7; }}
  .rpt-implication {{ background: #085041; color: #9FE1CB; }}
  .rpt-warning {{ background: #412402; border-color: #BA7517; }}
  .rpt-warning-label, .rpt-warning p {{ color: #FAC775; }}
  .rpt-rec-block {{ background: #042C53; }}
  .rpt-rec p, .rpt-rec-label {{ color: #B5D4F4; }}
  .rpt-tag-small {{ background: #444441; color: #D3D1C7; }}
  .rpt-bar-track {{ background: #444441; }}
  .rpt-bar-fill {{ background: #D3D1C7; }}
  .rpt-nav a {{ color: #85B7EB; }}
}}
</style>
</head>
<body>
<div class="container">
'''


def find_latest_report(kind):
    """가장 최근 {kind} 리포트 JSON 파일 찾기"""
    report_dir = DATA_DIR / kind
    if not report_dir.exists():
        return None
    candidates = sorted(report_dir.glob("*.json"))
    if not candidates:
        return None
    latest = candidates[-1]
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 일일 페이지 (index.html)
    by_date = load_recent_days()
    if not by_date:
        print("저장된 JSON이 없습니다. 기본 페이지 생성.")
        html_out = render_empty_page("수집 대기 중")
    else:
        total = sum(len(v) for v in by_date.values())
        if total == 0:
            latest_str = max(by_date.keys())
            print(f"최근 {len(by_date)}일치 파일은 있으나 카드가 없음.")
            html_out = render_empty_page(format_date_ko(latest_str))
        else:
            html_out = render_page(by_date)
            print(f"✓ 최근 {len(by_date)}일치 / {total}개 카드 렌더링")
    (DOCS_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"✓ docs/index.html 작성")

    # 2. 주간/월간/분기 페이지
    for kind in ("weekly", "monthly", "quarterly"):
        report = find_latest_report(kind)
        html = render_report_page(report, kind)
        (DOCS_DIR / f"{kind}.html").write_text(html, encoding="utf-8")
        if report:
            print(f"✓ docs/{kind}.html 작성 (period: {report.get('period_id')})")
        else:
            print(f"✓ docs/{kind}.html 작성 (빈 페이지)")


if __name__ == "__main__":
    main()
