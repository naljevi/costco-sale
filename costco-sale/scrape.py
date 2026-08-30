#!/usr/bin/env python3
"""코스트코 코리아 공식 사이트에서 할인 상품을 모아 data.json으로 저장한다.

상품 타일을 '상품 링크(a 태그)'를 기준으로 찾는다.
가격이 들어 있는 가장 작은 조각을 집으면 '100g당 708원' 같은
단위가격 표시가 상품으로 잡히기 때문이다.

로그에 타일 원문 샘플을 남긴다. 추출 규칙을 맞출 때 필요하다.
"""

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
MIN_ITEMS = 25
SAMPLE = 6          # 로그에 남길 타일 샘플 수
DEBUG_LINES = 50

SOURCES = [
    ("스페셜 할인", "https://www.costco.co.kr/Special-Price-Offers/c/SpecialPriceOffers"),
    ("바이어 추천", "https://www.costco.co.kr/Buyers-Pick/c/BuyersPick"),
]
EVENTS_URL = "https://www.costco.co.kr/events"

PRICE_RE = re.compile(r"([0-9][0-9,]{2,})\s*원")
RATE_RE = re.compile(r"\b([1-9][0-9]?)\s*%")
UNIT_RE = re.compile(r"당\s*$|당\s*[0-9]")          # '100g당 708원' 류
NOISE_RE = re.compile(
    r"장바구니|바로구매|재고|배송|무료|회원가|정상가|할인가|온라인가|"
    r"품절|수량|선택|비교|찜|리뷰|평점|더보기|자세히"
)

JS_TILES = """
() => {
  const out = [];
  const seen = new Set();
  const priceRe = /[0-9][0-9,]{2,}\\s*원/;
  const hrefRe = /\\/p\\/|\\/product|\\/\\d{6,}/i;
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (!hrefRe.test(href)) continue;
    let el = a, tile = null;
    for (let i = 0; i < 6 && el; i++) {
      const t = (el.innerText || '').trim();
      if (t.length >= 10 && t.length <= 400 && priceRe.test(t)) { tile = el; break; }
      el = el.parentElement;
    }
    if (!tile) continue;
    const text = (tile.innerText || '').trim();
    if (!text || seen.has(href)) continue;
    seen.add(href);
    out.push({ href: href, text: text });
  }
  return out;
}
"""


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_tile(tile: dict, category: str, base: str) -> dict | None:
    lines = [clean(l) for l in tile["text"].split("\n")]
    lines = [l for l in lines if l]

    # 가격: '~당' 이 붙은 줄(단위가격)은 제외한다
    prices = []
    for line in lines:
        if "당" in line and PRICE_RE.search(line):
            continue
        prices += [int(m.replace(",", "")) for m in PRICE_RE.findall(line)]
    prices = [p for p in prices if p >= 500]
    if not prices:
        return None
    price = min(prices)

    rates = [int(m) for m in RATE_RE.findall(tile["text"]) if int(m) <= 90]
    rate = max(rates) if rates else 0

    # 상품명: 가격도 % 도 없고, 안내 문구도 아닌 줄 중 가장 긴 것
    cands = [
        l for l in lines
        if not PRICE_RE.search(l)
        and not RATE_RE.search(l)
        and not UNIT_RE.search(l)
        and not NOISE_RE.search(l)
        and len(l) >= 4
    ]
    if not cands:
        return None
    name = max(cands, key=len)

    href = tile["href"]
    url = href if href.startswith("http") else base.rstrip("/") + "/" + href.lstrip("/")

    return {"c": category, "n": name[:90], "p": price, "r": rate, "e": "", "u": url}


def scrape_listing(page, label: str, url: str) -> list[dict]:
    print(f"  {label} 접속")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(3000)

    for _ in range(15):
        before = page.evaluate("document.body.scrollHeight")
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(1500)
        for sel in ["button:has-text('더보기')", "a:has-text('더보기')", "text=더 보기"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click(timeout=2000)
                    page.wait_for_timeout(1500)
            except Exception:
                pass
        if page.evaluate("document.body.scrollHeight") == before:
            break

    tiles = page.evaluate(JS_TILES)
    print(f"  {label}: 상품 링크 타일 {len(tiles)}개")

    for t in tiles[:SAMPLE]:
        print(f"  [샘플] href={t['href'][:70]}")
        for line in t["text"].split("\n")[:6]:
            if line.strip():
                print(f"         | {line.strip()[:90]}")

    items = []
    for t in tiles:
        parsed = parse_tile(t, label, "https://www.costco.co.kr")
        if parsed:
            items.append(parsed)
    print(f"  {label}: 상품 {len(items)}건")

    if not tiles:
        print(f"  --- {label} 화면 텍스트 ---")
        body = page.evaluate("document.body.innerText || ''")
        for line in [l for l in body.split("\n") if l.strip()][:DEBUG_LINES]:
            print(f"  | {line[:110]}")
        print("  --- 여기까지 ---")
    return items


def scrape_events(page, today: date) -> list[dict]:
    print("  매장 행사 접속")
    page.goto(EVENTS_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    body = page.evaluate("document.body.innerText || ''")
    lines = [clean(l) for l in body.split("\n") if clean(l)]

    end = ""
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일[^~]{0,10}~[^0-9]{0,10}(\d{1,2})\s*월\s*(\d{1,2})\s*일", body)
    if m:
        try:
            end = date(today.year, int(m.group(3)), int(m.group(4))).isoformat()
        except ValueError:
            end = ""

    items = []
    for i, line in enumerate(lines):
        pm = PRICE_RE.search(line)
        if not pm or "할인" not in line:
            continue
        cut = int(pm.group(1).replace(",", ""))
        if cut < 500:
            continue
        # 할인액 줄 앞뒤에서 상품명 후보를 찾는다
        near = lines[max(0, i - 2): i + 3]
        cands = [
            l for l in near
            if not PRICE_RE.search(l) and not NOISE_RE.search(l)
            and not re.fullmatch(r"[\d\s,./~월일()-]+", l) and len(l) >= 4
        ]
        if not cands:
            continue
        items.append({
            "c": "매장 행사", "n": max(cands, key=len)[:90],
            "p": 0, "r": 0, "e": end, "u": EVENTS_URL, "cut": cut,
        })

    print(f"  매장 행사: {len(items)}건 (종료일 {end or '미확인'})")
    if len(items) < 3:
        print("  --- 매장 행사 화면 텍스트 ---")
        for line in lines[:DEBUG_LINES]:
            print(f"  | {line[:110]}")
        print("  --- 여기까지 ---")
    return items


def main() -> int:
    today = datetime.now(KST).date()
    print(f"수집 시작 — 기준일 {today}")
    all_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ko-KR",
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        for label, url in SOURCES:
            try:
                all_items.extend(scrape_listing(page, label, url))
            except Exception as e:                     # noqa: BLE001
                print(f"  {label} 실패: {e}", file=sys.stderr)
        try:
            all_items.extend(scrape_events(page, today))
        except Exception as e:                         # noqa: BLE001
            print(f"  매장 행사 실패: {e}", file=sys.stderr)

        browser.close()

    seen, merged = set(), []
    for it in all_items:
        key = (it["n"], it["p"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(it)

    print(f"총 {len(merged)}건")
    if len(merged) < MIN_ITEMS:
        print(f"수집 실패: {len(merged)}건은 하한({MIN_ITEMS})보다 적습니다.", file=sys.stderr)
        return 1

    merged.sort(key=lambda x: (-x["r"], x["p"]))
    payload = {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "count": len(merged),
        "items": merged,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json 저장 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
