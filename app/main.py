"""
main.py — FastAPI 앱 진입점

uvicorn app.main:app --reload --port 8000

내장 스케줄러: 매일 오전 08:00(KST) 자동 수집 실행
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.api.routes import router, _run_scrape_task
from app.config import SERVER_HOST, SERVER_PORT, TIMEZONE, setup_logger

logger = setup_logger("main")

# ── 스케줄러 인스턴스 (모듈 수준) ──
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def scheduled_daily_scrape():
    """매일 오전 8시 자동 수집 태스크"""
    logger.info("⏰ [스케줄러] 매일 오전 8시 자동 수집 시작")
    try:
        await _run_scrape_task()
        logger.info("⏰ [스케줄러] 자동 수집 완료")
    except Exception as e:
        logger.error(f"⏰ [스케줄러] 자동 수집 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 스케줄러 관리"""
    # 시작
    logger.info("=== AI 정책 기사 스크랩 시스템 시작 ===")
    logger.info(f"서버: http://{SERVER_HOST}:{SERVER_PORT}")
    logger.info("대시보드: http://localhost:8000")

    # 매일 오전 8시 스케줄 등록
    scheduler.add_job(
        scheduled_daily_scrape,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_scrape",
        name="매일 오전 8시 AI 기사 자동 수집",
        replace_existing=True,
    )
    scheduler.start()

    next_run = scheduler.get_job("daily_scrape").next_run_time
    logger.info(f"⏰ 스케줄러 등록 완료 — 다음 실행: {next_run}")

    yield

    # 종료
    scheduler.shutdown(wait=False)
    logger.info("=== 시스템 종료 ===")


app = FastAPI(
    title="AI 정책 기사 자동 스크랩 시스템",
    description="서울AI플랫폼 AI 정책 게시판 자동 수집 및 동향지 제작 지원",
    version="2.0.0",
    lifespan=lifespan,
)

# 라우트 등록
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )
