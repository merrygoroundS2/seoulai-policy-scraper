"""
auth.py — 로그인 및 세션 관리

최초 1회 수동 로그인 후 storageState를 재사용하는 전략.
세션 만료 시 자동 재로그인, CAPTCHA 감지 시 수동 개입 안내.
"""

import asyncio
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import (
    LOGIN_ID,
    LOGIN_PW,
    LOGIN_URL,
    BASE_URL,
    SELECTORS,
    MAX_RETRY,
    RETRY_DELAY,
    setup_logger,
)
from app.scraper.browser import BrowserManager

logger = setup_logger("auth")


class AuthManager:
    """로그인/세션 관리를 담당하는 클래스"""

    def __init__(self, browser_manager: BrowserManager):
        self.bm = browser_manager

    async def check_session(self) -> bool:
        """현재 세션이 유효한지 확인한다."""
        page = self.bm.page
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)

            # 로그인 상태면 '로그아웃' 링크가 존재하거나 '로그아웃' 텍스트 노출됨
            logout_by_text = await page.locator("text=로그아웃").count()
            logout_el = await page.query_selector(SELECTORS["login_success_marker"])
            if logout_by_text > 0 or logout_el:
                logger.info("세션 유효 — 로그인 상태 확인됨")
                return True

            # 로그인 링크가 보이면 미로그인 상태
            login_link = await page.query_selector('a[href*="login"]')
            if login_link:
                logger.info("세션 만료 — 로그인 필요")
                return False

            logger.warning("세션 상태 판별 불가 — 로그인 시도 권장")
            return False

        except Exception as e:
            logger.error(f"세션 확인 중 오류: {e}")
            return False

    async def login(self, username: str = None, password: str = None) -> bool:
        """ID/PW를 사용하여 로그인한다. CAPTCHA 발생 시 사용자가 직접 브라우저 창에서 로그인 완료할 수 있도록 대기한다."""
        login_id = username or LOGIN_ID
        login_pw = password or LOGIN_PW

        if not login_id or not login_pw:
            logger.error(
                "로그인 정보 미설정. ID/PW를 전달하거나 .env 파일에 설정하세요."
            )
            return False

        page = self.bm.page

        try:
            logger.info("로그인 페이지 이동 및 자동 입력 시도")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # ID 입력
            id_input = await page.query_selector(SELECTORS["login_id_input"])
            if id_input:
                await id_input.fill("")
                await id_input.type(login_id, delay=50)
            else:
                await page.fill('input[type="text"]', login_id)

            # PW 입력
            pw_input = await page.query_selector(SELECTORS["login_pw_input"])
            if pw_input:
                await pw_input.fill("")
                await pw_input.type(login_pw, delay=50)
            else:
                await page.fill('input[type="password"]', login_pw)

            # 로그인 버튼 클릭 시도 (여러 방법)
            submitted = False
            for selector in [
                SELECTORS["login_submit_btn"],
                'input[type="submit"]',
                'button:has-text("로그인")',
                'a:has-text("로그인")',
            ]:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    submitted = True
                    break

            if not submitted:
                await page.keyboard.press("Enter")

            # 대기 및 로그인 완료 감시 (사용자 수동 개입/CAPTCHA 해결 대기)
            logger.info("로그인 완료 여부 감시 시작 (사용자 CAPTCHA 수동 해결 대기 — 최대 90초)")
            max_iterations = 5 if self.bm.headless else 45  # Headless면 10초(5 * 2초), Headed면 90초(45 * 2초) 대기
            for i in range(max_iterations):
                await asyncio.sleep(2)
                
                # 로그인 성공 여부 검사
                if await self._verify_login(page):
                    logger.info("로그인 성공 감지 완료!")
                    await self.bm.save_session()
                    return True
                
                # CAPTCHA 감지 로깅 및 Headless 시 조기 종료
                if await self._detect_captcha(page):
                    if self.bm.headless:
                        logger.error("Headless 모드에서 CAPTCHA(보안문자)가 감지되어 로그인 시도를 즉시 종료합니다. (수동 개입 필요)")
                        return False
                    logger.warning(
                        f"[{i+1}/45] CAPTCHA(보안문자) 감지됨! 화면에 뜬 브라우저 창에서 수동으로 CAPTCHA를 풀고 로그인을 진행해 주세요."
                    )

                # 로그인 오류 메시지 감지 및 Headless 시 조기 종료
                login_error = await self._get_login_error(page)
                if login_error:
                    if self.bm.headless:
                        logger.error(f"Headless 모드에서 로그인 오류 감지: {login_error.strip()}")
                        return False
 
            logger.error("로그인 대기 시간 초과 (90초)")
            return False

        except Exception as e:
            logger.error(f"로그인 처리 중 예외 발생: {e}")
            return False

    async def ensure_logged_in(self) -> bool:
        """세션 확인 → 필요하면 로그인 시도"""
        if await self.check_session():
            return True
        return await self.login()

    async def _verify_login(self, page: Page) -> bool:
        """로그인 성공 여부를 확인한다."""
        try:
            # 1. 화면 전체에서 '로그아웃'이라는 텍스트가 노출되는지 신속 감지
            logout_by_text = await page.locator("text=로그아웃").count()
            if logout_by_text > 0:
                return True

            # 2. 지정된 CSS 셀렉터 마커 확인
            logout_el = await page.query_selector(SELECTORS["login_success_marker"])
            if logout_el:
                return True

            # 3. 로그인 폼 URL(/login.do)에서 완전히 벗어난 상태인지 체크
            current_url = page.url
            if "login.do" not in current_url:
                # 헤더 우측 상단에 '로그인' 버튼이 여전히 남아있는지 확인
                header_login = await page.query_selector('.header-button a[href*="login"]')
                if not header_login:
                    # 로그인 버튼 링크가 사라졌다면 로그인 세션이 생성된 것으로 판정
                    return True

            return False
        except Exception as e:
            logger.error(f"로그인 성공 검증 중 오류: {e}")
            return False

    async def _detect_captcha(self, page: Page) -> bool:
        """CAPTCHA 존재 여부를 확인한다."""
        try:
            captcha = await page.query_selector(SELECTORS["captcha_element"])
            return captcha is not None
        except Exception:
            return False

    async def _get_login_error(self, page: Page) -> Optional[str]:
        """로그인 실패 시 에러 메시지를 추출한다."""
        try:
            # alert 다이얼로그가 뜨는 경우
            for selector in [
                ".error-message",
                ".alert-danger",
                ".login-error",
                "#loginError",
            ]:
                el = await page.query_selector(selector)
                if el:
                    return await el.text_content()
            return None
        except Exception:
            return None
