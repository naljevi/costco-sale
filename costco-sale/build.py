#!/usr/bin/env python3
"""data.json을 template.html에 끼워 넣어 table/index.html을 만든다.

표는 /table/ 경로에 둔다.
사이트 첫 주소(/)는 _redirects 설정에 따라 블로그로 넘어간다.
"""

import json
import os
import sys
from datetime import datetime

OUT_DIR = "table"
OUT_FILE = os.path.join(OUT_DIR, "index.html")


def main() -> int:
    try:
        with open("data.json", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        print("data.json이 없습니다. scrape.py를 먼저 실행하세요.", file=sys.stderr)
        return 1

    items = payload.get("items", [])
    if not items:
        print("data.json에 상품이 없습니다.", file=sys.stderr)
        return 1

    with open("template.html", encoding="utf-8") as f:
        html = f.read()

    generated = payload.get("generated", "")
    try:
        pretty = datetime.fromisoformat(generated).strftime("%Y년 %m월 %d일 %H:%M")
    except ValueError:
        pretty = generated

    html = (
        html.replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        .replace("__TODAY__", payload.get("today", ""))
        .replace("__COUNT__", str(len(items)))
        .replace("__GENERATED__", pretty)
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{OUT_FILE} 생성 완료 — {len(items)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
