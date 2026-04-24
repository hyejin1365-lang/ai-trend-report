"""
정적 사이트 빌더
data/*.json → public/index.html

가장 최근 일일 JSON을 읽어 카드 UI로 렌더링.
"""

import html
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
PUBLIC_DIR = REPO_ROOT / "public"


def find_latest_daily_json():
    """가장 최근 일일 JSON 파일 찾기"""
    if not DATA_DIR.exists():
        return None, None
    candidates = []
    for f in DATA_DIR.rglob("*.json"):
        # seen.json이나 주간/월간/분기는 제외
        if f.name == "seen.json":
            continue
        if "weekly" in str(f) or "monthly" in str(f) or "quarterly" in str(f):
            continue
        # 파일명이 YYYY-MM-DD.json 형태인지 확인
        try:
            datetime.strptime(f.stem, "%Y-%m-%d")
            candidates.append(f)
        except ValueError:
            continue

    if not candidates:
        return None, None
    latest = max(candidates, key=lambda p: p.stem)
    cards = json.loads(latest.read_text(encoding="utf-8"))
    return cards, latest.stem


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


def render_page(cards, date_str):
    importance_order = {"핵심": 0, "주목": 1, "참고": 2}
    cards.sort(key=lambda c: importance_order.get(c.get("importance", "참고"), 3))

    hero_cards = [c for c in cards if c.get("importance") == "핵심"]
    other_cards = [c for c in cards if c.get("importance") != "핵심"]

    hero_html = "\n".join(render_hero_card(c) for c in hero_cards)
    if not hero_html:
        hero_html = '<p class="empty-note">오늘은 핵심 업데이트가 없습니다.</p>'

    others_html = "\n".join(render_mini_card(c) for c in other_cards)
    if not others_html:
        others_html = '<p class="empty-note">추가 업데이트가 없습니다.</p>'

    date_display = format_date_ko(date_str)
    total = len(cards)
    other_count = len(other_cards)

    return PAGE_TEMPLATE.format(
        date_display=esc(date_display),
        total_count=total,
        other_count=other_count,
        hero_section=hero_html,
        others_section=others_html,
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
    <h1>오늘의 업데이트</h1>
    <div class="sub">공간 콘텐츠 제작 기술 트렌드 · 총 {total_count}건</div>
  </div>
  <div class="head-date">{date_display}</div>
</header>

<div class="section-title">오늘의 핵심</div>
{hero_section}

<div class="section-title">전체 업데이트 · {other_count}건</div>
<div class="grid">
{others_section}
</div>

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


def main():
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    cards, date_str = find_latest_daily_json()

    if cards is None:
        print("저장된 JSON이 없습니다. 기본 페이지 생성.")
        html_out = render_empty_page("수집 대기 중")
    elif len(cards) == 0:
        print(f"{date_str}: 수집된 카드 없음. '업데이트 없음' 페이지 생성.")
        html_out = render_empty_page(format_date_ko(date_str))
    else:
        html_out = render_page(cards, date_str)
        print(f"✓ {len(cards)}개 카드를 페이지로 렌더링 ({date_str})")

    (PUBLIC_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"✓ public/index.html 작성 완료")


if __name__ == "__main__":
    main()
