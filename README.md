# 🤖 AI 정책 기사 자동 스크랩 시스템

서울AI플랫폼(seoulai.saif.or.kr)의 AI 정책 게시판에서 **"정부부처·청·위원회"** 범주의 기사를 매일 자동 수집하여 엑셀에 누적 저장하는 동향지 제작 지원 자동화 시스템입니다.

## 🌐 원클릭 클라우드 배포 (배포링크 만들기)

아래 버튼을 누르면 별도의 로컬 설치 없이 클라우드 서버(Render.com)에 즉시 배포되어, 다른 사람들과 함께 사용할 수 있는 **공유 배포링크(URL)**를 10초 만에 생성할 수 있습니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/merrygoroundS2/seoulai-policy-scraper)

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🔐 자동 로그인 | Playwright 기반 브라우저 자동화 + storageState 세션 재사용 |
| 📰 기사 수집 | "정부부처·청·위원회" 필터 자동 적용 → 당일 신규 기사만 수집 |
| 📄 본문 추출 | 원문 링크 이동 → HTML 정제 → 순수 텍스트 추출 |
| 📊 엑셀 저장 | 3개 시트(원문/실행로그/에러로그) 자동 누적 |
| 🔑 키워드 추출 | AI 용어 사전 기반 자동 키워드 태깅 |
| 🎯 관련도 점수 | AI 관련도 자동 계산 (0.0~1.0) |
| 🖥️ 대시보드 | 웹 관리 화면 (즉시 수집, 기사 조회, 다운로드) |
| ⏰ 예약 실행 | cron / launchd / GitHub Actions 지원 |
| 🛡️ 예외 처리 | 로그인 실패, 세션 만료, 네트워크 오류 등 8가지 시나리오 대응 |

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 가상환경 생성 (권장)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 계정 정보 입력
```

### 3. 최초 로그인 (세션 저장)

```bash
python scripts/login_manual.py
```

### 4. 수집 테스트

```bash
# 오늘 기사 수집
python scripts/run_scrape.py

# 특정 날짜 수집
python scripts/run_scrape.py --date 2026-07-12

# 목록만 수집 (본문 생략)
python scripts/run_scrape.py --no-body
```

### 5. 대시보드 실행

```bash
uvicorn app.main:app --reload --port 8000
# 브라우저에서 http://localhost:8000 접속
```

## 📁 프로젝트 구조

```
동향지 자동 스크랩/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── config.py            # 환경변수 + 셀렉터 + 설정
│   ├── scraper/
│   │   ├── browser.py       # Playwright 브라우저 관리
│   │   ├── auth.py          # 로그인/세션 관리
│   │   ├── collector.py     # 기사 목록 수집 핵심 로직
│   │   ├── parser.py        # 상세 본문 파싱
│   │   └── cleaner.py       # 본문 정제/키워드 추출
│   ├── storage/
│   │   └── excel_manager.py # 엑셀 읽기/쓰기/중복관리
│   ├── api/
│   │   └── routes.py        # API 라우트 정의
│   └── templates/
│       └── dashboard.html   # 관리자 대시보드 UI
├── auth/                    # 세션 상태 (gitignore)
├── output/                  # 엑셀 출력 (gitignore)
├── logs/                    # 로그 파일 (gitignore)
├── scripts/
│   ├── login_manual.py      # 최초 수동 로그인
│   └── run_scrape.py        # CLI 수집 실행
├── scheduler/
│   ├── github_actions.yml   # GitHub Actions 워크플로우
│   └── cron_setup.md        # cron/launchd 설정 가이드
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 📊 엑셀 출력 형식

| 시트 | 용도 | 주요 컬럼 |
|------|------|-----------|
| `raw_articles` | 기사 원문 누적 | 기사ID, 제목, 기관명, 게시일, URL, 본문, 키워드, AI관련도, 요약 |
| `run_log` | 실행 이력 | 실행일시, 발견건수, 신규건수, 실패건수, 소요시간 |
| `error_log` | 에러 기록 | 실패URL, 에러메시지, 발생시각 |

## 🔧 API 엔드포인트

| 메서드 | 경로 | 기능 |
|--------|------|------|
| `GET` | `/` | 대시보드 UI |
| `POST` | `/api/scrape` | 즉시 수집 실행 |
| `GET` | `/api/status` | 수집 상태 조회 |
| `GET` | `/api/articles` | 최근 기사 목록 |
| `GET` | `/api/download` | 엑셀 다운로드 |
| `GET` | `/api/session` | 세션 상태 |
| `GET` | `/api/errors` | 에러 로그 |
| `GET` | `/api/logs` | 실행 로그 |

## ⏰ 예약 실행 설정

자세한 설정 방법은 [scheduler/cron_setup.md](scheduler/cron_setup.md)를 참조하세요.

### macOS (launchd 권장)
```bash
# plist 등록
launchctl load ~/Library/LaunchAgents/com.seoulai.scraper.plist
```

### GitHub Actions
```bash
# .github/workflows/ 에 github_actions.yml 복사
# GitHub Secrets에 SEOULAI_LOGIN_ID, SEOULAI_LOGIN_PW 설정
```

## 🔒 보안 주의사항

- `.env` 파일은 절대 Git에 커밋하지 마세요
- `auth/storage_state.json`은 세션 토큰을 포함합니다
- 수집 간격을 적절히 유지하세요 (기본 3초)
- 로그에 비밀번호가 출력되지 않도록 주의하세요

## 📝 라이선스

내부 업무 자동화 도구 — 비공개
