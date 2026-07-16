"""
browser.py — Playwright 브라우저 매니저

싱글턴 패턴으로 브라우저 인스턴스를 관리한다.
storageState 기반 세션 복원을 지원한다.
"""

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from app.config import (
    HEADLESS,
    BROWSER_TIMEOUT,
    AUTH_STATE_FILEPATH,
    setup_logger,
)

logger = setup_logger("browser")


class BrowserManager:
    """Playwright Chromium 브라우저를 관리하는 싱글턴 클래스"""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.headless: bool = True

    async def start(self, headless: Optional[bool] = None) -> "BrowserManager":
        """브라우저를 시작하고 컨텍스트를 생성한다."""
        if headless is None:
            headless = HEADLESS
        self.headless = headless

        logger.info(f"브라우저 시작 (headless={self.headless})")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # storageState 파일이 있으면 세션 복원
        storage_state = None
        if AUTH_STATE_FILEPATH.exists():
            storage_state = str(AUTH_STATE_FILEPATH)
            logger.info("저장된 세션 상태 로드")

        self._context = await self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        self._context.set_default_timeout(BROWSER_TIMEOUT)
        self._page = await self._context.new_page()

        logger.info("브라우저 초기화 완료")
        return self

    async def save_session(self) -> None:
        """현재 세션 상태를 파일로 저장한다."""
        if self._context is None:
            logger.warning("세션 저장 실패: 브라우저 컨텍스트 없음")
            return

        AUTH_STATE_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(AUTH_STATE_FILEPATH))
        logger.info(f"세션 상태 저장 완료: {AUTH_STATE_FILEPATH}")

    async def new_page(self) -> Page:
        """새 페이지(탭)를 생성한다."""
        if self._context is None:
            raise RuntimeError("브라우저가 시작되지 않았습니다. start()를 먼저 호출하세요.")
        return await self._context.new_page()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("브라우저가 시작되지 않았습니다.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("브라우저가 시작되지 않았습니다.")
        return self._context

    async def close(self) -> None:
        """브라우저를 안전하게 종료한다."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("브라우저 종료 완료")
        except Exception as e:
            logger.error(f"브라우저 종료 중 오류: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False
