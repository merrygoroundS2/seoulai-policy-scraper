"""
login_manual.py — 최초 수동 로그인 스크립트

headed 모드로 브라우저를 열어 사용자가 직접 로그인하고,
로그인 성공 후 storageState를 저장한다.

사용법:
    python scripts/login_manual.py
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import LOGIN_URL, BASE_URL, AUTH_STATE_FILEPATH, LOGIN_ID, LOGIN_PW
from app.scraper.browser import BrowserManager
from app.scraper.auth import AuthManager


async def manual_login():
    """수동 로그인 프로세스"""
    print("=" * 60)
    print("  서울AI플랫폼 로그인 — 세션 저장 스크립트")
    print("=" * 60)
    print()

    bm = BrowserManager()
    await bm.start(headless=False)  # headed 모드로 열기

    page = bm.page

    try:
        # 방법 1: .env에 계정 정보가 있으면 자동 로그인 시도
        if LOGIN_ID and LOGIN_PW:
            print(f"[INFO] .env에서 계정 정보 감지 → 자동 로그인 시도")
            auth = AuthManager(bm)
            success = await auth.login()

            if success:
                print()
                print("✅ 자동 로그인 성공! 세션이 저장되었습니다.")
                print(f"   저장 위치: {AUTH_STATE_FILEPATH}")
                await bm.close()
                return

            print("[WARN] 자동 로그인 실패 → 수동 로그인으로 전환")
            print()

        # 방법 2: 수동 로그인
        print("[INFO] 브라우저 창이 열렸습니다.")
        print(f"[INFO] 로그인 페이지로 이동합니다: {LOGIN_URL}")
        print()

        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print("📌 브라우저 창에서 직접 로그인해주세요.")
        print("   - CAPTCHA가 있으면 수동으로 해결하세요.")
        print("   - 2차 인증이 있으면 완료해주세요.")
        print()
        print("로그인 완료 후 아무 키나 누르면 세션을 저장합니다...")
        print("(또는 Ctrl+C로 취소)")

        # 사용자 입력 대기
        await asyncio.get_event_loop().run_in_executor(None, input)

        # 로그인 확인
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 로그인 상태 확인
        logout_el = await page.query_selector('a[href*="logout"], .logout')
        if logout_el:
            await bm.save_session()
            print()
            print("✅ 로그인 확인 완료! 세션이 저장되었습니다.")
            print(f"   저장 위치: {AUTH_STATE_FILEPATH}")
        else:
            print()
            print("⚠️  로그인 상태를 확인할 수 없습니다.")
            print("   그래도 세션을 저장할까요? (y/n)")

            answer = await asyncio.get_event_loop().run_in_executor(None, input)
            if answer.lower() in ("y", "yes", "ㅛ"):
                await bm.save_session()
                print(f"   세션 저장 완료: {AUTH_STATE_FILEPATH}")
            else:
                print("   세션 저장을 건너뜁니다.")

    except KeyboardInterrupt:
        print("\n\n취소되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
    finally:
        await bm.close()
        print("\n브라우저를 닫았습니다.")


if __name__ == "__main__":
    asyncio.run(manual_login())
