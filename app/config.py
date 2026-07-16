"""
config.py — 환경변수 로드 및 전역 설정 관리

모든 설정을 한 곳에서 관리하여 유지보수성을 높인다.
사이트 셀렉터도 여기서 관리 → 사이트 구조 변경 시 이 파일만 수정.
"""

import os
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import pytz

# .env 로드 (프로젝트 루트 기준)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ──────────────────────────────────────────────
# 타임존
# ──────────────────────────────────────────────
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Seoul"))


def now_kst() -> datetime:
    """현재 한국 시간 반환"""
    return datetime.now(TIMEZONE)


# ──────────────────────────────────────────────
# 로그인 정보 (절대 코드에 하드코딩 금지)
# ──────────────────────────────────────────────
LOGIN_ID = os.getenv("SEOULAI_LOGIN_ID", "")
LOGIN_PW = os.getenv("SEOULAI_LOGIN_PW", "")

# ──────────────────────────────────────────────
# 사이트 URL
# ──────────────────────────────────────────────
BASE_URL = os.getenv("SEOULAI_BASE_URL", "https://seoulai.saif.or.kr")
LOGIN_URL = os.getenv("SEOULAI_LOGIN_URL", f"{BASE_URL}/hmpg/user/logi/login.do")
LIST_PAGE_URL = os.getenv("SEOULAI_LIST_URL", f"{BASE_URL}/hmpg/bpst/bpstListPage.do")
LIST_AJAX_URL = f"{BASE_URL}/hmpg/bpst/bpstListPgng"
DETAIL_AJAX_URL = f"{BASE_URL}/hmpg/bpst/bpstDetail"
SUMMARY_AJAX_URL = f"{BASE_URL}/hmpg/bpst/bpstPostSummary"

# ──────────────────────────────────────────────
# 수집 필터
# ──────────────────────────────────────────────
SCRAPE_FILTER_HMPG_NM = os.getenv(
    "SCRAPE_FILTER_HMPG_NM", "정부부처·청·위원회"
).split(",")

# ──────────────────────────────────────────────
# 파일 경로
# ──────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output")
OUTPUT_FILENAME = os.getenv("OUTPUT_FILENAME", "articles_daily.xlsx")
OUTPUT_FILEPATH = OUTPUT_DIR / OUTPUT_FILENAME

AUTH_DIR = PROJECT_ROOT / os.getenv("AUTH_DIR", "auth")
AUTH_STATE_FILE = os.getenv("AUTH_STATE_FILE", "storage_state.json")
AUTH_STATE_FILEPATH = AUTH_DIR / AUTH_STATE_FILE

LOG_DIR = PROJECT_ROOT / os.getenv("LOG_DIR", "logs")

# 디렉토리 자동 생성
for d in [OUTPUT_DIR, AUTH_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# Playwright 옵션
# ──────────────────────────────────────────────
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
PAGE_LOAD_DELAY = float(os.getenv("PAGE_LOAD_DELAY", "2"))
ARTICLE_FETCH_DELAY = float(os.getenv("ARTICLE_FETCH_DELAY", "3"))

# ──────────────────────────────────────────────
# 서버 설정
# ──────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# ──────────────────────────────────────────────
# CSS 셀렉터 (사이트 구조 변경 시 여기만 수정)
# ──────────────────────────────────────────────
SELECTORS = {
    # 로그인 페이지
    "login_id_input": 'input[name="mbr_id"], input[id="mbr_id"]',
    "login_pw_input": 'input[name="mbr_pswd"], input[id="mbr_pswd"]',
    "login_submit_btn": 'button[type="submit"], a.btn-login, .login-btn',
    "login_success_marker": 'a[href*="logout"], .logout',

    # 게시판 필터
    "filter_govt_checkbox": '#hmpg_nm_mi_3',
    "filter_check_all": '#check_all',
    "date_start": '#wrt_bgng_ymd',
    "date_end": '#wrt_end_ymd',
    "date_all_checkbox": '#check2_1',
    "search_btn": '#btnSearch',

    # 기사 목록 (AJAX 로딩 영역)
    "data_content": '#dataContent',
    "article_list_item": '.board-list li, .list-box li, .member-box > ul > li',
    "article_title": '.list-head p, .title, h5',
    "article_org": '.list-body li:has(b:contains("기관")) p',
    "article_date": '.list-body li:has(b:contains("등록일")) p',
    "article_link": 'a.inner[target="_blank"]',

    # 기사 상세
    "detail_body": '.view-body, .content-body, .detail-content',

    # 페이지네이션
    "pagination": '.paging-box, .pagination',
    "next_page": '.paging-box a.next, .pagination .next',

    # CAPTCHA 감지
    "captcha_element": '#captcha, .captcha, .g-recaptcha, iframe[src*="captcha"]',
}

# ──────────────────────────────────────────────
# 재시도 설정
# ──────────────────────────────────────────────
MAX_RETRY = 3
RETRY_DELAY = 5  # 초

# ──────────────────────────────────────────────
# AI 키워드 사전 — 2계층 구성
#   핵심: 제목 필터링 + 관련도 가중치 2.0
#   확장: 본문 분석 전용, 가중치 1.0
# ──────────────────────────────────────────────
AI_CORE_KEYWORDS = [
    "인공지능", "AI", "머신러닝", "딥러닝", "생성형", "GPT", "LLM",
    "자연어처리", "NLP", "컴퓨터비전", "자율주행", "로봇", "챗봇",
    "빅데이터", "디지털전환", "스마트시티", "디지털트윈",
    "초거대", "파운데이션", "멀티모달", "AX", "MCP",
]

AI_EXTENDED_KEYWORDS = [
    "데이터", "알고리즘", "클라우드", "IoT", "블록체인",
    "메타버스", "XR", "사이버보안", "개인정보", "윤리",
    "규제", "거버넌스", "플랫폼", "반도체", "GPU", "NPU",
]

# 하위 호환성을 위해 통합 목록도 유지
AI_KEYWORDS = AI_CORE_KEYWORDS + AI_EXTENDED_KEYWORDS

# AI 관련도 임계치 (이 값 이상인 기사만 엑셀에 저장)
AI_RELEVANCE_THRESHOLD = float(os.getenv("AI_RELEVANCE_THRESHOLD", "0.05"))

# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str = "scraper") -> logging.Logger:
    """로거 생성 — 파일 + 콘솔 동시 출력"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 파일 핸들러
    log_file = LOG_DIR / f"{name}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    # 콘솔 핸들러
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
