# 코스트코 할인표 자동 갱신

매일 오전 6시(한국 시간)에 GitHub이 알아서 코스트코 할인 데이터를 다시 모으고,
`index.html`을 새로 만들어 저장소에 커밋합니다.
저장소를 Netlify나 GitHub Pages에 연결해두면 커밋이 생길 때마다 사이트가 자동 배포됩니다.

사람이 할 일은 아래 세팅 한 번뿐입니다.

---

## 파일 구성

| 파일 | 역할 |
|---|---|
| `scrape.py` | 할인 데이터를 모아 `data.json`으로 저장 |
| `build.py` | `data.json`을 `template.html`에 끼워 `index.html` 생성 |
| `template.html` | 표 디자인과 검색·정렬 기능 |
| `.github/workflows/update.yml` | 매일 실행 스케줄 |
| `data.json`, `index.html` | 자동 생성물 (지금 들어 있는 건 8월 26일자 샘플) |

---

## 1단계 — 저장소 만들기

1. github.com 로그인 → 우측 상단 `+` → **New repository**
2. 이름: `costco-sale` (아무거나 괜찮습니다)
3. **Public**으로 두세요. Private이면 GitHub Pages가 유료 플랜에서만 됩니다
4. **Create repository**

## 2단계 — 파일 올리기

1. 만들어진 저장소 화면에서 **uploading an existing file** 클릭
2. 이 폴더의 파일을 **폴더째로** 끌어다 놓습니다
   `.github` 폴더가 같이 올라가야 합니다. 안 보이면 숨김 파일 보기를 켜세요
3. 아래 **Commit changes** 클릭

## 3단계 — Actions 권한 확인

1. 저장소 → **Settings** → 왼쪽 **Actions** → **General**
2. 맨 아래 **Workflow permissions**
3. **Read and write permissions** 선택 → **Save**

이걸 안 하면 GitHub이 갱신된 파일을 저장소에 커밋하지 못합니다.

## 4단계 — 손으로 한 번 돌려보기

1. 저장소 → **Actions** 탭
2. 왼쪽에서 **코스트코 할인표 갱신** 선택
3. 오른쪽 **Run workflow** → 초록 버튼 클릭
4. 2~3분 뒤 결과를 봅니다

- **초록 체크**: 성공. `data.json`과 `index.html`이 갱신됐습니다
- **빨간 X**: 로그를 열어 '데이터 수집' 단계의 메시지를 확인하세요

## 5단계 — 사이트에 연결

**Netlify를 쓰신다면**

1. app.netlify.com → **Add new project** → **Import an existing project**
2. GitHub 선택 → 방금 만든 저장소 선택
3. Build command는 **비워 둡니다**. Publish directory는 `.` (점 하나)
4. Deploy 후 **Make public**을 눌러 공개로 바꿉니다

**GitHub Pages를 쓰신다면**

1. 저장소 → Settings → **Pages**
2. Source를 `Deploy from a branch`, 브랜치는 `main`, 폴더는 `/ (root)`
3. `사용자명.github.io/저장소명` 주소가 생깁니다

둘 중 어느 쪽이든, 이후로는 매일 자동으로 갱신된 표가 그 주소에 반영됩니다.

---

## 실행 시각 바꾸기

`.github/workflows/update.yml`의 `cron` 값을 고칩니다. **UTC 기준**입니다.

| 원하는 한국 시간 | cron 값 |
|---|---|
| 오전 6시 | `0 21 * * *` |
| 오전 9시 | `0 0 * * *` |
| 오후 8시 | `0 11 * * *` |

GitHub 무료 계정의 스케줄은 서버가 붐비면 최대 한 시간까지 밀릴 수 있습니다.
정확한 정시 실행이 필요한 용도가 아니므로 문제되지 않습니다.

---

## 수집이 실패하면

`scrape.py`는 유효 상품이 80건 미만이면 **일부러 실패시킵니다.**
빈 표가 조용히 배포되는 것보다 실패가 낫기 때문입니다.
실패하면 GitHub이 등록된 메일로 알려 줍니다.

실패의 대부분은 데이터를 가져오는 사이트의 구조가 바뀐 경우입니다.
Actions 로그의 '데이터 수집' 단계에 카테고리별 수집 건수가 찍히니,
그 로그를 저에게 보여주시면 `scrape.py`를 고쳐 드리겠습니다.

수집이 실패해도 **이전 `index.html`은 그대로 남아 있습니다.**
사이트가 깨지지는 않고, 날짜만 예전 것으로 표시됩니다.

---

## 디자인이나 항목을 바꾸고 싶으면

`template.html`만 고치면 됩니다. 데이터 구조는 건드리지 않습니다.
상품 하나는 이런 형태입니다.

```
{ "c": "식품", "n": "상품명", "p": 9990, "r": 21, "e": "2026-08-30" }
```

`c`=분류, `n`=상품명, `p`=할인가, `r`=할인율(%), `e`=종료일.
