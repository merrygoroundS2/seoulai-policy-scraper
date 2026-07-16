"""
parser.py — 기사 상세 본문 파싱

기사 상세 페이지 또는 원문 외부 링크에서 본문을 추출한다.
"""

import asyncio
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import (
    BASE_URL,
    SELECTORS,
    ARTICLE_FETCH_DELAY,
    setup_logger,
)
from app.scraper.cleaner import clean_html, clean_text

logger = setup_logger("parser")


async def fetch_article_body(
    page: Page,
    detail_url: Optional[str] = None,
    hmpg_mng_no: Optional[str] = None,
    pst_no: Optional[str] = None,
) -> str:
    """기사 본문을 추출한다.

    전략:
    1. detail_url(원문 링크)이 있으면 해당 URL로 이동하여 본문 추출
    2. hmpg_mng_no + pst_no가 있으면 사이트 내 상세 페이지에서 추출
    3. 모두 실패하면 빈 문자열 반환
    """
    body_text = ""

    # 전략 1: 원문 링크로 이동
    if detail_url and detail_url.startswith("http"):
        body_text = await _fetch_from_external_url(page, detail_url)
        if body_text:
            return body_text

    # 전략 2: 사이트 내 상세 API 활용 (향후 구현)
    # 현재 사이트 구조상 아코디언 방식이므로, 목록 페이지에서
    # detailView() JS 함수를 호출하여 본문을 로드할 수 있다.
    # 단, 이 방식은 목록 페이지 컨텍스트에서만 동작.

    if not body_text:
        logger.warning(
            f"본문 추출 실패: url={detail_url}, "
            f"hmpg_mng_no={hmpg_mng_no}, pst_no={pst_no}"
        )

    return body_text


async def _fetch_from_external_url(page: Page, url: str) -> str:
    """외부 URL에서 기사 본문을 추출한다."""
    try:
        logger.debug(f"원문 페이지 접속: {url}")

        # 새 탭에서 열기 (현재 페이지 보존)
        new_page = await page.context.new_page()

        try:
            await new_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(ARTICLE_FETCH_DELAY)

            # 다양한 본문 셀렉터 시도
            body_html = await _extract_body_html(new_page)

            if body_html:
                cleaned = clean_html(body_html)
                if cleaned and len(cleaned) > 50:
                    logger.debug(f"본문 추출 성공: {len(cleaned)}자")
                    return cleaned

            # 폴백: 페이지 전체 텍스트에서 추출
            full_text = await new_page.inner_text("body")
            cleaned = clean_text(full_text)

            if cleaned and len(cleaned) > 50:
                logger.debug(f"전체 텍스트에서 본문 추출: {len(cleaned)}자")
                return cleaned

            logger.warning(f"본문이 너무 짧음: {url}")
            return cleaned

        finally:
            await new_page.close()

    except PlaywrightTimeout:
        logger.warning(f"원문 페이지 타임아웃: {url}")
        return ""
    except Exception as e:
        logger.error(f"원문 페이지 오류: {url} — {e}")
        return ""


async def _extract_body_html(page: Page) -> Optional[str]:
    """다양한 셀렉터로 본문 영역을 찾아 HTML을 반환한다."""
    # 일반적인 본문 영역 셀렉터들 (정부부처 보도자료 사이트 공통)
    body_selectors = [
        # 정부부처 보도자료 공통 (우선순위 높음)
        ".fr_view",
        ".view_con",
        ".view-body",
        ".view_body",
        ".content-body",
        ".bbs_detail",
        ".board_view",
        ".articleView",
        "#articleBody",

        # 일반적인 본문 영역
        ".article-body",
        ".detail-content",
        ".post-content",
        ".entry-content",
        ".news_body",
        ".view_txt",
        ".brd_viewer",

        # 최종 폴백 (범위 넓음)
        "#content",
        "article",
        "main",
        '[role="main"]',
    ]

    for selector in body_selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                html = await el.inner_html()
                if html and len(html.strip()) > 100:
                    return html
        except Exception:
            continue

    return None


async def fetch_body_from_accordion(
    page: Page,
    hmpg_mng_no: str,
    pst_no: str,
) -> str:
    """게시판 목록 페이지에서 아코디언을 열어 본문을 추출한다.

    사이트의 detailView() JS 함수를 호출하는 방식.
    목록 페이지 컨텍스트에서만 동작한다.
    """
    try:
        # 아코디언 열기
        await page.evaluate(
            f"detailView('{hmpg_mng_no}', '{pst_no}', 'MI')"
        )
        await asyncio.sleep(3)

        # AI 요약 텍스트 추출
        summary_el = await page.query_selector(
            f"#aiSummaryList_{hmpg_mng_no}_{pst_no}"
        )
        if summary_el:
            text = await summary_el.inner_text()
            if text and "요약 중" not in text:
                return clean_text(text)

        # 아코디언 닫기
        await page.evaluate(
            f"detailView('{hmpg_mng_no}', '{pst_no}', 'MI')"
        )

        return ""

    except Exception as e:
        logger.error(f"아코디언 본문 추출 오류: {e}")
        return ""
