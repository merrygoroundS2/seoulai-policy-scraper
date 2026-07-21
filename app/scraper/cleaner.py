"""
cleaner.py — 본문 정제 및 AI 키워드 필터링

수집된 HTML 본문에서 불필요한 요소를 제거하고,
AI 관련 키워드를 추출하여 메타데이터를 생성한다.

2단계 AI 필터링:
  1. 제목 기반 사전 필터링 (핵심 키워드 매칭)
  2. 본문 기반 최종 필터링 (가중치 관련도 점수)
"""

import re
from typing import List

from bs4 import BeautifulSoup

from app.config import AI_CORE_KEYWORDS, AI_EXTENDED_KEYWORDS, setup_logger

logger = setup_logger("cleaner")

# ──────────────────────────────────────────────
# 제거 대상 태그/클래스/ID 패턴
# ──────────────────────────────────────────────
REMOVE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]
REMOVE_CLASSES = [
    "menu", "nav", "footer", "header", "sidebar", "share", "sns",
    "comment", "reply", "banner", "ad", "popup", "modal", "cookie",
    "skipnavi", "chat-aside", "filter-box", "paging",
    # 정부부처 보도자료 사이트 공통 잡음 영역
    "popular", "realtime", "ranking", "relation", "prev-next",
    "article-relation", "policy-now", "bottom-banner", "site-info",
]
REMOVE_IDS = [
    "skipNavi", "gnb", "lnb", "topBanner", "bottomBanner",
    "footer", "snsShare", "articleRelation",
]

# 불필요한 문구 패턴 (정규식)
NOISE_PATTERNS = [
    r"공유하기.*$",
    r"카카오톡.*$",
    r"페이스북.*$",
    r"트위터.*$",
    r"URL\s?복사.*$",
    r"인쇄하기.*$",
    r"담당\s?부서.*$",
    r"문의\s?전화.*$",
    r"출처\s?:.*$",
    r"저작권.*$",
    r"Copyright.*$",
    r"^\s*이전글.*$",
    r"^\s*다음글.*$",
    r"^\s*이전기사.*$",
    r"^\s*다음기사.*$",
    r"^\s*목록으로.*$",
    r"\[.*뉴스\]",
    # 정부부처 보도자료 사이트 공통 잡음
    r"이 누리집은 대한민국.*$",
    r"대한민국 정책브리핑.*$",
    r"실시간 인기뉴스.*$",
    r"정책 NOW.*$",
    r"사실은 이렇습니다.*$",
    r"관련사이트.*$",
    r"^\s*홈으로\s*$",
    r"^\s*브리핑룸\s*$",
    r"^\s*보도자료\s*$",
    r"^\s*콘텐츠 영역\s*$",
    r"^\s*공유열기\s*$",
    r"^\s*바로보기\s*$",
    r"^\s*내려받기\s*$",
    r"^\s*공지사항\s*$",
    r"^\s*더보기\s*$",
    r"^\s*정책자료\s*$",
    r"^\s*구독.*참여\s*$",
    r"공공누리.*자유이용.*$",
    r"담당자안내.*$",
    r"이전다음기사.*$",
    r"본문\s*바로가기.*$",
    r"메인메뉴\s*바로가기.*$",
    r"사이트\s*이동경로.*$",
    r"댓글수.*이동.*$",
    r"^\d{2}\.\d{2}\.\s*\d{2}:\d{2}\s*기준$",
    r"^\s*NEW\s*$",
    r"^\s*순위.*$",
    r"^\s*단계.*$",
    r"개인정보처리방침.*$",
    r"이메일\s*수집거부.*$",
    r"자주\s*묻는\s*질문.*$",
    r"전화\s*\d{2,3}-\d{3,4}-\d{4}.*$",
    r"오늘의\s*멀티미디어.*$",
    r"하단\s*배너\s*영역.*$",
    r"^\s*이전보기\s*$",
    r"^\s*다음보기\s*$",
    r"인기뉴스\s*$",
]


# ──────────────────────────────────────────────
# 제목 기반 1단계 필터링
# ──────────────────────────────────────────────
def is_ai_related_title(title: str) -> bool:
    """제목에 핵심 AI 키워드가 포함되어 있는지 확인한다.

    1단계 필터링: 핵심 키워(AI_CORE_KEYWORDS)만 사용하여
    "데이터", "개인정보" 등 범용어로 인한 오탐을 방지한다.
    """
    if not title:
        return False

    title_lower = title.lower()
    for keyword in AI_CORE_KEYWORDS:
        if keyword.lower() in title_lower:
            return True
    return False


def is_central_government(org_name: str) -> bool:
    """기관명이 중앙행정기관(정부부처·청·위원회)에 해당하는지 판별한다.

    지방자치단체(도, 시, 구 등), 연구기관/진흥원(STEPI, SPRI, NIA 등),
    해외기관(OECD, 미국 등)에서 업로드된 자료를 2차적으로 필터링하여 걸러낸다.
    """
    if not org_name:
        return False

    org_name = org_name.strip()

    # 1. 중앙행정기관의 변형 명칭 또는 핵심 부처 예외 리스트
    central_exceptions = [
        "국무조정실", "국무총리비서실", "감사원", "대통령실", "방위사업청", "문화재청",
        "국가유산청", "재정경제부", "산업통상부", "방송미디어통신위원회", "국가기후위기대응위원회",
        "지식재산처", "기후에너지환경부", "우주항공청"
    ]
    if any(exception in org_name for exception in central_exceptions):
        return True

    # 2. 지자체(도청, 시청 등), 산하 연구/진흥기관 및 해외기관을 지시하는 단어 차단
    block_words = [
        "특별시", "광역시", "자치시", "자치도", "도청", "시청", "군청", "구청", "교육청",
        "연구소", "연구원", "진흥원", "평가원", "센터", "협회", "공사", "공단", "재단",
        "테크노파크", "대학", "학교", "학회", "의회", "연구회", "소방본부", "보건소"
    ]
    if any(word in org_name for word in block_words):
        return False

    # 3. 중앙 부처/처/청/위원회 어미 확인
    if org_name.endswith("부") or org_name.endswith("처") or org_name.endswith("청") or org_name.endswith("위원회"):
        return True

    return False


# ──────────────────────────────────────────────
# HTML/텍스트 정제
# ──────────────────────────────────────────────
def clean_html(html: str) -> str:
    """HTML에서 본문 텍스트를 추출하고 정제한다."""
    if not html or not html.strip():
        return ""

    soup = BeautifulSoup(html, "lxml")

    # 불필요한 태그 제거
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 불필요한 클래스 가진 요소 제거
    for cls_pattern in REMOVE_CLASSES:
        for el in soup.find_all(class_=re.compile(cls_pattern, re.I)):
            el.decompose()

    # 불필요한 ID 가진 요소 제거
    for id_pattern in REMOVE_IDS:
        el = soup.find(id=re.compile(id_pattern, re.I))
        if el:
            el.decompose()

    # 텍스트 추출
    text = soup.get_text(separator="\n")

    return clean_text(text)


def clean_text(text: str) -> str:
    """텍스트에서 불필요한 문구를 제거하고 정리한다."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 너무 짧은 줄 스킵 (메뉴 등)
        if len(line) < 3:
            continue

        # 노이즈 패턴 매칭
        skip = False
        for pattern in NOISE_PATTERNS:
            if re.search(pattern, line, re.MULTILINE | re.IGNORECASE):
                skip = True
                break
        if skip:
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    # 연속 공백 정리
    result = re.sub(r" {2,}", " ", result)
    # 연속 줄바꿈 정리 (3줄 이상 → 2줄)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


# ──────────────────────────────────────────────
# 키워드 추출 및 AI 관련도 계산
# ──────────────────────────────────────────────
def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """본문에서 AI 관련 키워드를 추출한다.

    핵심 키워드를 우선 정렬하고, 확장 키워드는 후순위로 배치한다.
    """
    if not text:
        return []

    text_lower = text.lower()

    core_found = []
    for keyword in AI_CORE_KEYWORDS:
        count = text_lower.count(keyword.lower())
        if count > 0:
            core_found.append((keyword, count))

    extended_found = []
    for keyword in AI_EXTENDED_KEYWORDS:
        count = text_lower.count(keyword.lower())
        if count > 0:
            extended_found.append((keyword, count))

    # 핵심 키워드 먼저, 각 그룹 내에서 빈도수 내림차순
    core_found.sort(key=lambda x: x[1], reverse=True)
    extended_found.sort(key=lambda x: x[1], reverse=True)

    result = [kw for kw, _ in core_found] + [kw for kw, _ in extended_found]
    return result[:top_n]


def calculate_ai_relevance(text: str) -> float:
    """본문의 AI 관련도 점수를 계산한다 (0.0 ~ 1.0).

    가중치 기반:
      - 핵심 키워드 등장 → 가중치 2.0
      - 확장 키워드 등장 → 가중치 1.0
    전체 단어 대비 가중 키워드 밀도로 정규화.
    """
    if not text:
        return 0.0

    words = text.split()
    total = len(words)
    if total == 0:
        return 0.0

    text_lower = text.lower()

    weighted_count = 0.0
    for keyword in AI_CORE_KEYWORDS:
        weighted_count += text_lower.count(keyword.lower()) * 2.0
    for keyword in AI_EXTENDED_KEYWORDS:
        weighted_count += text_lower.count(keyword.lower()) * 1.0

    # 정규화 (최대 1.0)
    score = min(weighted_count / max(total * 0.1, 1), 1.0)
    return round(score, 3)


def generate_summary_placeholder(text: str, max_lines: int = 3) -> str:
    """간단한 추출 요약 (핵심 문장 N개).

    첫 줄이 사이트 헤더 잡음인 경우 건너뛴다.
    향후 AI 요약 API로 대체 가능.
    """
    if not text:
        return ""

    # 잡음 패턴에 해당하는 첫 줄 스킵
    noise_starts = [
        "이 누리집", "대한민국", "본문 바로가기", "메인메뉴",
        "홈으로", "브리핑룸", "콘텐츠 영역",
    ]

    # 문장 분리
    sentences = re.split(r'(?<=[.!?。])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # 잡음 문장 제거
    filtered = []
    for s in sentences:
        is_noise = False
        for noise in noise_starts:
            if s.startswith(noise):
                is_noise = True
                break
        if not is_noise:
            filtered.append(s)

    if not filtered:
        # 문장 분리 실패 시 첫 300자
        return text[:300] + "..." if len(text) > 300 else text

    return " ".join(filtered[:max_lines])
