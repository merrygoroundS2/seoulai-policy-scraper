"""
collector.py — 기사 목록 수집 핵심 로직

서울AI플랫폼 AI 정책 게시판에서
"정부부처·청·위원회" 필터를 적용한 기사 목록을 수집한다.

2단계 AI 필터링 파이프라인:
  1단계: 제목에 AI 핵심 키워드가 있는 기사만 본문 수집
  2단계: 본문 AI 관련도가 임계치 이상인 기사만 엑셀 저장
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Set

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import (
    LIST_PAGE_URL,
    SELECTORS,
    PAGE_LOAD_DELAY,
    ARTICLE_FETCH_DELAY,
    AI_RELEVANCE_THRESHOLD,
    now_kst,
    setup_logger,
)
from app.scraper.browser import BrowserManager
from app.scraper.auth import AuthManager
from app.scraper.parser import fetch_article_body
from app.scraper.cleaner import (
    is_ai_related_title,
    extract_keywords,
    calculate_ai_relevance,
    generate_summary_placeholder,
)

logger = setup_logger("collector")


@dataclass
class Article:
    """수집된 기사 데이터 구조"""
    article_id: str = ""
    title: str = ""
    organization: str = ""
    publish_date: str = ""
    detail_url: str = ""
    body_text: str = ""
    collected_at: str = ""
    keywords: str = ""        # 쉼표 구분 문자열
    ai_relevance: float = 0.0
    summary: str = ""
    category: str = "정부부처·청·위원회"
    hmpg_mng_no: str = ""
    pst_no: str = ""


@dataclass
class ScrapeResult:
    """수집 실행 결과"""
    run_time: str = ""
    total_found: int = 0
    new_count: int = 0
    skipped_count: int = 0
    filtered_out_title: int = 0   # 제목 필터로 제외된 건수
    filtered_out_score: int = 0   # 관련도 미달로 제외된 건수
    error_count: int = 0
    elapsed_seconds: float = 0.0
    articles: List[Article] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)


async def run_collection(
    existing_ids: Optional[Set[str]] = None,
    target_date: Optional[str] = None,
    fetch_body: bool = True,
) -> ScrapeResult:
    """기사 수집을 실행한다.

    2단계 AI 필터링 파이프라인:
      1단계: 제목에 AI 핵심 키워드 포함 여부 확인 → 미포함 스킵
      2단계: 본문 수집 후 AI 관련도 점수 확인 → 임계치 미달 스킵
    """
    if existing_ids is None:
        existing_ids = set()

    if target_date is None:
        target_date = now_kst().strftime("%Y-%m-%d")

    result = ScrapeResult(run_time=now_kst().isoformat())
    start_time = datetime.now()

    logger.info(f"=== 기사 수집 시작 (대상일: {target_date}) ===")

    async with BrowserManager() as bm:
        # 1. 로그인 확인
        auth = AuthManager(bm)
        logged_in = await auth.ensure_logged_in()
        if not logged_in:
            logger.warning("로그인 실패 — 비로그인 상태로 수집 시도")

        # 2. 게시판 페이지 이동 + 필터 적용
        page = bm.page
        articles_data = await _load_filtered_list(page, target_date)

        result.total_found = len(articles_data)
        logger.info(f"목록에서 {result.total_found}건 발견")

        if result.total_found == 0:
            logger.info("수집할 기사가 없습니다. (주말/공휴일일 수 있음)")
            elapsed = (datetime.now() - start_time).total_seconds()
            result.elapsed_seconds = round(elapsed, 1)
            return result

        # 3. 각 기사 처리 (2단계 AI 필터링)
        for idx, article_data in enumerate(articles_data, 1):
            article_id = article_data.get("article_id", "")
            title = article_data.get("title", "")

            # 중복 확인
            if article_id in existing_ids:
                logger.debug(f"  [{idx}] 중복 스킵: {title[:30]}")
                result.skipped_count += 1
                continue

            # ── 1단계: 제목 기반 AI 필터링 ──
            if not is_ai_related_title(title):
                logger.debug(f"  [{idx}] AI 무관(제목): {title[:40]}")
                result.filtered_out_title += 1
                continue

            try:
                article = Article(
                    article_id=article_id,
                    title=title,
                    organization=article_data.get("organization", ""),
                    publish_date=article_data.get("publish_date", ""),
                    detail_url=article_data.get("detail_url", ""),
                    collected_at=now_kst().isoformat(),
                    hmpg_mng_no=article_data.get("hmpg_mng_no", ""),
                    pst_no=article_data.get("pst_no", ""),
                )

                # 본문 수집
                if fetch_body and article.detail_url:
                    logger.info(
                        f"  [{idx}/{result.total_found}] 본문 수집: "
                        f"{article.title[:40]}..."
                    )
                    article.body_text = await fetch_article_body(
                        page,
                        detail_url=article.detail_url,
                        hmpg_mng_no=article.hmpg_mng_no,
                        pst_no=article.pst_no,
                    )

                    # 키워드/관련도/요약
                    if article.body_text:
                        keywords = extract_keywords(article.body_text)
                        article.keywords = ", ".join(keywords)
                        article.ai_relevance = calculate_ai_relevance(article.body_text)
                        article.summary = generate_summary_placeholder(article.body_text)

                    # ── 2단계: 본문 AI 관련도 필터링 ──
                    if article.ai_relevance < AI_RELEVANCE_THRESHOLD:
                        logger.debug(
                            f"  [{idx}] AI 관련도 미달({article.ai_relevance:.3f}): "
                            f"{title[:30]}"
                        )
                        result.filtered_out_score += 1
                        continue

                    # 요청 간 딜레이 (서버 부하 방지)
                    await asyncio.sleep(ARTICLE_FETCH_DELAY)

                result.articles.append(article)
                result.new_count += 1
                logger.info(
                    f"  [{idx}] ✓ AI 기사 수집: {article.title[:40]} "
                    f"(관련도: {article.ai_relevance:.3f}, 키워드: {article.keywords[:30]})"
                )

            except Exception as e:
                result.error_count += 1
                error_info = {
                    "url": article_data.get("detail_url", ""),
                    "title": title,
                    "error": str(e),
                    "timestamp": now_kst().isoformat(),
                }
                result.errors.append(error_info)
                logger.error(f"  [{idx}] 수집 실패: {e}")

    elapsed = (datetime.now() - start_time).total_seconds()
    result.elapsed_seconds = round(elapsed, 1)

    logger.info(
        f"=== 수집 완료 ===\n"
        f"  발견: {result.total_found}건\n"
        f"  AI 기사(신규): {result.new_count}건\n"
        f"  중복: {result.skipped_count}건\n"
        f"  제목 필터 제외: {result.filtered_out_title}건\n"
        f"  관련도 미달: {result.filtered_out_score}건\n"
        f"  실패: {result.error_count}건\n"
        f"  소요: {result.elapsed_seconds}초"
    )

    return result


async def _load_filtered_list(
    page: Page,
    target_date: str,
) -> List[dict]:
    """게시판에서 필터를 적용한 기사 목록을 로드한다."""

    logger.info(f"게시판 페이지 이동: {LIST_PAGE_URL}")
    await page.goto(LIST_PAGE_URL, wait_until="domcontentloaded")
    await asyncio.sleep(PAGE_LOAD_DELAY)

    # 초기 AJAX 로딩 대기
    try:
        await page.wait_for_selector(
            SELECTORS["data_content"],
            state="attached",
            timeout=10000,
        )
        await asyncio.sleep(2)  # 콘텐츠 렌더링 대기
    except PlaywrightTimeout:
        logger.warning("기사 목록 로딩 타임아웃")

    # JS 코드를 사용하여 필터 및 날짜 주입 후 다이렉트 검색 실행
    logger.info("JS 코드를 통해 필터 및 날짜 설정 주입")
    await page.evaluate(f"""
        () => {{
            // 1. 분야 '전체' 체크 해제
            const checkAll = document.getElementById('check_all');
            if (checkAll && checkAll.checked) {{
                checkAll.checked = false;
            }}

            // 2. '정부부처·청·위원회' 체크박스 체크 및 상태 변경
            const cb = document.getElementById('hmpg_nm_mi_3');
            if (cb) {{
                cb.checked = true;
                if (typeof hmpgNmSearchOptionChange === 'function') {{
                    hmpgNmSearchOptionChange(cb, 'MI');
                }}
            }}

            // 3. 기간 '전체' 체크 해제
            const dateAll = document.getElementById('check2_1');
            if (dateAll && dateAll.checked) {{
                dateAll.checked = false;
            }}

            // 4. 날짜 설정 및 jQuery change 이벤트 트리거
            const startInput = document.getElementById('wrt_bgng_ymd');
            const endInput = document.getElementById('wrt_end_ymd');
            if (startInput && endInput) {{
                startInput.value = '{target_date}';
                endInput.value = '{target_date}';
                if (window.jQuery) {{
                    window.jQuery(startInput).trigger('change');
                    window.jQuery(endInput).trigger('change');
                }}
            }}

            // 5. 검색 실행
            if (typeof search === 'function') {{
                search();
            }}
        }}
    """)

    # 검색 실행 대기
    await asyncio.sleep(3)

    # AJAX 응답 대기
    try:
        await page.wait_for_selector(
            f"{SELECTORS['data_content']} li, {SELECTORS['data_content']} .no-data",
            state="attached",
            timeout=15000,
        )
    except PlaywrightTimeout:
        logger.warning("필터 적용 후 목록 로딩 타임아웃 — 수동으로 검색 버튼 클릭 시도")
        search_btn = await page.query_selector(SELECTORS["search_btn"])
        if search_btn:
            await search_btn.click()
            await asyncio.sleep(5)

    await asyncio.sleep(2)

    # 기사 목록 파싱
    return await _parse_article_list(page)


async def _parse_article_list(page: Page) -> List[dict]:
    """렌더링된 기사 목록에서 데이터를 추출한다."""
    articles = []

    # 데이터 영역 확인
    data_content = await page.query_selector(SELECTORS["data_content"])
    if not data_content:
        logger.warning("데이터 영역(#dataContent)을 찾을 수 없음")
        return articles

    content_html = await data_content.inner_html()
    if not content_html.strip():
        logger.info("데이터 영역이 비어있음")
        return articles

    # JavaScript를 사용하여 목록 항목을 구조적으로 추출
    try:
        items = await page.evaluate("""
            () => {
                const results = [];
                const container = document.getElementById('dataContent');
                if (!container) return results;

                // 기사 카드 본체(최상위 li)만 엄격하게 필터링
                const allLis = Array.from(container.querySelectorAll('li'));
                const listItems = allLis.filter(li => {
                    // 1. 페이지네이션 영역 제외
                    if (li.closest('.paging-box') || li.closest('.pagination')) return false;

                    // 2. id에 언더스코어(_)가 포함되어 있는 최상위 카드 li이거나,
                    //    하위에 detailView 클릭 이벤트를 트리거할 수 있는 엘리먼트가 존재해야 함
                    const id = li.getAttribute('id');
                    const hasValidId = id && id.includes('_') && !id.startsWith('bpstSimilarityList') && !id.startsWith('aiSummary');
                    const hasClick = li.querySelector('[onclick*="detailView"]') !== null;

                    return hasValidId || hasClick;
                });

                listItems.forEach(li => {
                    const item = {};

                    // 아코디언 클릭 이벤트에서 hmpg_mng_no, pst_no 추출
                    const clickEl = li.querySelector('[onclick*="detailView"]');
                    if (clickEl) {
                        const onclick = clickEl.getAttribute('onclick');
                        const match = onclick.match(/detailView\\s*\\(\\s*'([^']*)'\\s*,\\s*'([^']*)'\\s*,\\s*'([^']*)'/)
                        if (match) {
                            item.hmpg_mng_no = match[1];
                            item.pst_no = match[2];
                            item.ai_bbs_inst_se_cd = match[3];
                        }
                    }

                    // ID가 hmpg_mng_no_pst_no 형태인 요소에서 추출
                    const id = li.getAttribute('id');
                    if (id && id.includes('_')) {
                        const parts = id.split('_');
                        if (parts.length >= 2 && !item.hmpg_mng_no) {
                            item.hmpg_mng_no = parts[0];
                            item.pst_no = parts.slice(1).join('_');
                        }
                    }

                    // 제목 (p.subject 우선, 폴백으로 .list-head p)
                    const subjectEl = li.querySelector('p.subject');
                    const fallbackEl = li.querySelector('.list-head p');
                    const titleEl = subjectEl || fallbackEl;
                    item.title = titleEl ? titleEl.textContent.trim() : '';

                    // 기관명 및 등록일(게시일) — .left-bottom 내부의 li들
                    const metaLis = li.querySelectorAll('.left-bottom li, .list-head li');
                    metaLis.forEach(mLi => {
                        const label = mLi.querySelector('b');
                        const value = mLi.querySelector('p');
                        if (label && value) {
                            const labelText = label.textContent.trim();
                            if (labelText.includes('기관') || labelText.includes('출처')) {
                                item.organization = value.textContent.trim();
                            }
                            if (labelText.includes('등록일') || labelText.includes('날짜') || labelText.includes('일자')) {
                                item.publish_date = value.textContent.trim();
                            }
                        }
                    });

                    // 원문 링크
                    const linkEl = li.querySelector('a[target="_blank"]');
                    if (linkEl) {
                        item.detail_url = linkEl.getAttribute('href') || '';
                    }

                    // 유효한 데이터만 추가
                    if (item.title && item.title.length > 0) {
                        item.article_id = (item.hmpg_mng_no || '') + '_' + (item.pst_no || '');
                        results.push(item);
                    }
                });

                return results;
            }
        """)

        logger.info(f"목록에서 {len(items)}건 파싱됨")
        return items

    except Exception as e:
        logger.error(f"목록 파싱 오류: {e}")
        return []
