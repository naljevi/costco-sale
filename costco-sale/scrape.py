#!/usr/bin/env python3
"""코스트코 주간 할인 데이터를 수집해 data.json으로 저장한다.

수집처: cocohotdeals.com 카테고리별 상품 목록
방식:   페이지에서 '가격(원)'과 '할인율(%)'을 동시에 가진 블록을 찾아
        상품명·할인가·할인율·종료일을 뽑는다.
        특정 클래스명에 의존하지 않으므로 사이트 디자인이 바뀌어도
        구조가 크게 달라지지 않는 한 계속 동작한다.

실패 조건: 수집 건수가 MIN_ITEMS 미만이면 종료 코드 1로 실패시킨다.
          (사이트 구조가 바뀐 것이므로 조용히 빈 표를 배포하면 안 된다)
"""

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE = "https://cocohotdeals.com/categories/{}/products/"

CATEGORIES = [
    "식품",
    "건강-영양제",
    "홈-키친",
    "화장품-미용-제지",
    "의류-가방-잡화",
    "유아동-완구-반려동물용품",
    "공구-생활-자동차",
    "가구-침구-인테리어",
    "디지털-tv-컴퓨터",
    "대형-생활가전",
    "스포츠-헬스-캠핑",
    "파티오-정원-창고",
    "문구-사무",
    "보석-시계-액세서리",
]

MIN_ITEMS = 80          # 이보다 적게 나오면 수집 실패로 본다
MAX_PAGES = 12          # 카테고리당 최대 페이지
REQUEST_GAP = 1.0       # 요청 간격(초). 상대 서버에 대한 예의다
KST = timezone(timedelta(hours=9))

PRICE_RE = re.compile(r"([0-9][0-9,]{2,})\s*원")
RATE_RE = re.compile(r"\b([1-9][0-9]?)\s*%")
END_RE = re.compile(r"~?\s*(1[0-2]|[1-9])\s*\.\s*([0-3]?[0-9])\b")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; costco-sale-table/1.0; personal blog use)",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch(url: str) -> str | None:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except Exception as e:                       # noqa: BLE001
            print(f"  재시도 {attempt + 1}/3 ({e})", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def resolve_end_date(month: int, day: int, today: date) -> str:
    """'8.30' 같은 표기를 YYYY-MM-DD로 바꾼다.

    표시된 달이 지금보다 6개월 이상 과거면 내년으로 본다.
    (12월 말에 '1.5'가 나오는 경우를 처리하기 위함)
    """
    year = today.year
    if month < today.month - 6:
        year += 1
    elif month > today.month + 6:
        year -= 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def extract_items(html: str, category: str, today: date) -> list[dict]:
    """가격과 할인율을 함께 가진 최소 단위 블록을 상품 하나로 본다."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    candidates = []
    for el in soup.find_all(["li", "article", "tr", "div", "a"]):
        text = el.get_text(" ", strip=True)
        if len(text) > 400 or len(text) < 8:
            continue
        if not PRICE_RE.search(text) or not RATE_RE.search(text):
            continue
        # 같은 조건을 만족하는 자식이 있으면 부모는 버린다 (최소 블록만 남김)
        if any(
            PRICE_RE.search(c.get_text(" ", strip=True) or "")
            and RATE_RE.search(c.get_text(" ", strip=True) or "")
            for c in el.find_all(["li", "article", "tr", "div", "a"], recursive=True)
        ):
            continue
        candidates.append(text)

    items, seen = [], set()
    for text in candidates:
        prices = [int(m.replace(",", "")) for m in PRICE_RE.findall(text)]
        rates = [int(m) for m in RATE_RE.findall(text)]
        if not prices or not rates:
            continue
        price = min(prices)                 # 정상가가 같이 있으면 낮은 쪽이 할인가
        rate = max(r for r in rates if r <= 90)

        end = ""
        tail = text[text.rfind(f"{rate}%"):] if f"{rate}%" in text else text
        m = END_RE.search(tail) or END_RE.search(text)
        if m:
            end = resolve_end_date(int(m.group(1)), int(m.group(2)), today)

        # 상품명: 가격·할인율·종료일 표기를 걷어낸 나머지 중 가장 긴 조각
        name = PRICE_RE.sub(" ", text)
        name = RATE_RE.sub(" ", name)
        name = END_RE.sub(" ", name)
        name = re.sub(r"[|·▶◀]|할인가|정상가|할인율|종료|남음|일\s*$", " ", name)
        name = clean(name)
        if len(name) < 3 or price < 300:
            continue

        key = (name, price)
        if key in seen:
            continue
        seen.add(key)
        items.append({"c": category, "n": name[:90], "p": price, "r": rate, "e": end})

    return items


def scrape_category(label: str, today: date) -> list[dict]:
    slug = quote(label, safe="-")
    out, prev_signature = [], None
    for page in range(1, MAX_PAGES + 1):
        url = BASE.format(slug) if page == 1 else BASE.format(slug) + f"?page={page}"
        html = fetch(url)
        time.sleep(REQUEST_GAP)
        if not html:
            break
        found = extract_items(html, label, today)
        if not found:
            break
        signature = {(i["n"], i["p"]) for i in found}
        if signature == prev_signature:      # 같은 내용이 반복되면 마지막 페이지
            break
        prev_signature = signature
        out.extend(found)
    print(f"  {label}: {len(out)}건")
    return out


def main() -> int:
    today = datetime.now(KST).date()
    print(f"수집 시작 — 기준일 {today}")

    all_items, seen = [], set()
    for label in CATEGORIES:
        try:
            for item in scrape_category(label, today):
                key = (item["n"], item["p"])
                if key not in seen:
                    seen.add(key)
                    all_items.append(item)
        except Exception as e:                # noqa: BLE001
            print(f"  {label} 실패: {e}", file=sys.stderr)

    # 이미 끝난 행사는 버린다
    live = [i for i in all_items if not i["e"] or i["e"] >= today.isoformat()]

    print(f"총 {len(all_items)}건 수집, 유효 {len(live)}건")
    if len(live) < MIN_ITEMS:
        print(
            f"수집 실패: 유효 {len(live)}건은 하한({MIN_ITEMS})보다 적습니다.\n"
            "사이트 구조가 바뀌었을 가능성이 높습니다. scrape.py를 점검하세요.",
            file=sys.stderr,
        )
        return 1

    live.sort(key=lambda x: (-x["r"], x["p"]))
    payload = {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "count": len(live),
        "items": live,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json 저장 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
