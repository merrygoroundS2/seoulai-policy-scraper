"""
routes.py — FastAPI API 라우트 정의

대시보드 UI 서빙 + REST API 엔드포인트를 제공한다.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import (
    OUTPUT_FILEPATH,
    AUTH_STATE_FILEPATH,
    now_kst,
    setup_logger,
)
from app.storage.excel_manager import ExcelManager
from app.scraper.collector import run_collection, ScrapeResult
from app.scraper.browser import BrowserManager
from app.scraper.auth import AuthManager

logger = setup_logger("api")
router = APIRouter()

# 템플릿 엔진
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# 전역 상태: 수집 진행 중 여부
_scraping_in_progress = False
_last_result: dict = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class ScrapeRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def remove_file(path: str):
    """임시 파일 삭제 헬퍼 함수"""
    try:
        Path(path).unlink(missing_ok=True)
        logger.info(f"임시 파일 삭제 완료: {path}")
    except Exception as e:
        logger.error(f"임시 파일 삭제 실패: {path} - {e}")


def _get_next_schedule_time() -> Optional[str]:
    """스케줄러의 다음 실행 시간을 반환한다."""
    try:
        from app.main import scheduler
        job = scheduler.get_job("daily_scrape")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """관리자 대시보드 메인 페이지"""
    excel = ExcelManager()

    if start_date or end_date:
        recent_articles = excel.get_filtered_articles(start_date=start_date, end_date=end_date, limit=100)
    else:
        recent_articles = excel.get_recent_articles(limit=20)

    context = {
        "request": request,
        "last_run_time": excel.get_last_run_time() or "실행 이력 없음",
        "today_count": excel.get_today_count(),
        "session_active": AUTH_STATE_FILEPATH.exists(),
        "is_scraping": _scraping_in_progress,
        "recent_articles": recent_articles,
        "run_logs": excel.get_run_logs(limit=5),
        "error_logs": excel.get_error_logs(limit=10),
        "current_time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date_val": start_date or "",
        "end_date_val": end_date or "",
        "next_schedule_time": _get_next_schedule_time() or "스케줄러 미등록",
    }

    return templates.TemplateResponse(request, "dashboard.html", context)


@router.post("/api/login")
async def api_login(data: LoginRequest):
    """대시보드 로그인 요청을 처리하여 storageState 세션을 저장한다."""
    logger.info(f"대시보드 로그인 요청 수신: ID={data.username}")

    try:
        bm = BrowserManager()
        await bm.start(headless=False)

        try:
            auth = AuthManager(bm)
            success = await auth.login(username=data.username, password=data.password)

            if success:
                logger.info("대시보드 로그인 성공 및 세션 저장됨")
                return {"status": "success", "message": "로그인 및 세션 갱신 성공"}
            else:
                logger.warning("대시보드 로그인 실패")
                return JSONResponse(
                    status_code=401,
                    content={"status": "fail", "message": "로그인 실패 (CAPTCHA 해결 실패 또는 대기 시간 초과)"}
                )
        finally:
            await bm.close()

    except Exception as e:
        logger.error(f"로그인 처리 중 오류 발생: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"로그인 처리 오류: {str(e)}"}
        )


@router.post("/api/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks, data: Optional[ScrapeRequest] = None):
    """즉시 수집 실행 (비동기 백그라운드)"""
    global _scraping_in_progress

    if _scraping_in_progress:
        return JSONResponse(
            status_code=409,
            content={"status": "busy", "message": "수집이 이미 진행 중입니다."},
        )

    start_date = data.start_date if data else None
    end_date = data.end_date if data else None

    _scraping_in_progress = True
    background_tasks.add_task(_run_scrape_task, start_date, end_date)

    return {"status": "started", "message": "수집이 시작되었습니다. (AI 기사만 필터링하여 저장)"}


async def _run_scrape_task(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """백그라운드에서 수집을 실행한다. (날짜 범위 수집 + AI 필터링)"""
    global _scraping_in_progress, _last_result

    try:
        excel = ExcelManager()
        existing_ids = excel.get_existing_article_ids()

        # 수집할 날짜 배열 생성
        dates = []
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")
                curr = start
                while curr <= end:
                    dates.append(curr.strftime("%Y-%m-%d"))
                    curr += timedelta(days=1)
            except ValueError as e:
                logger.error(f"수집 날짜 파싱 오류: {e}")
                dates = [now_kst().strftime("%Y-%m-%d")]
        elif start_date:
            dates = [start_date]
        else:
            dates = [now_kst().strftime("%Y-%m-%d")]

        total_new_articles = []
        total_found = 0
        skipped_count = 0
        filtered_title = 0
        filtered_score = 0
        error_count = 0
        errors = []
        start_time = datetime.now()

        # 각 날짜에 대해 수집 실행
        for target_date in dates:
            logger.info(f"백그라운드 수집 실행 날짜: {target_date}")
            result: ScrapeResult = await run_collection(
                existing_ids=existing_ids,
                target_date=target_date,
                fetch_body=True,
            )

            if result.articles:
                total_new_articles.extend(result.articles)
                for art in result.articles:
                    existing_ids.add(art.article_id)

            total_found += result.total_found
            skipped_count += result.skipped_count
            filtered_title += result.filtered_out_title
            filtered_score += result.filtered_out_score
            error_count += result.error_count
            if result.errors:
                errors.extend(result.errors)

        elapsed_seconds = round((datetime.now() - start_time).total_seconds(), 1)

        # 엑셀 누적 저장
        if total_new_articles:
            excel.save_articles(total_new_articles)

        run_time_str = now_kst().isoformat()

        # 실행 로그 저장
        excel.save_run_log(
            run_time=run_time_str,
            total_found=total_found,
            new_count=len(total_new_articles),
            skipped_count=skipped_count,
            error_count=error_count,
            elapsed_seconds=elapsed_seconds,
        )

        # 에러 로그 저장
        if errors:
            excel.save_error_log(errors)

        _last_result = {
            "status": "completed",
            "run_time": run_time_str,
            "total_found": total_found,
            "new_count": len(total_new_articles),
            "filtered_title": filtered_title,
            "filtered_score": filtered_score,
            "error_count": error_count,
            "elapsed_seconds": elapsed_seconds,
        }

        logger.info(
            f"수집 태스크 완료: AI 기사 {len(total_new_articles)}건 저장 "
            f"(전체 {total_found}건 중 제목필터 {filtered_title}건·관련도필터 {filtered_score}건 제외)"
        )

    except Exception as e:
        logger.error(f"수집 태스크 실패: {e}")
        _last_result = {
            "status": "error",
            "message": str(e),
            "run_time": now_kst().isoformat(),
        }

    finally:
        _scraping_in_progress = False


@router.get("/api/status")
async def get_status():
    """현재 수집 상태 및 마지막 실행 결과"""
    excel = ExcelManager()

    return {
        "is_scraping": _scraping_in_progress,
        "last_result": _last_result,
        "last_run_time": excel.get_last_run_time(),
        "today_count": excel.get_today_count(),
        "session_active": AUTH_STATE_FILEPATH.exists(),
        "excel_exists": OUTPUT_FILEPATH.exists(),
        "current_time": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        "next_schedule_time": _get_next_schedule_time(),
    }


@router.get("/api/articles")
async def get_articles(limit: int = 20, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """최근 수집 기사 목록 (필터링 지원)"""
    excel = ExcelManager()
    if start_date or end_date:
        articles = excel.get_filtered_articles(start_date=start_date, end_date=end_date, limit=limit)
    else:
        articles = excel.get_recent_articles(limit=limit)
    return {"articles": articles, "count": len(articles)}


@router.get("/api/download")
async def download_excel(background_tasks: BackgroundTasks, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """엑셀 파일 다운로드 (날짜 필터 시 부분 추출 파일 반환 후 삭제)"""
    excel = ExcelManager()

    if not OUTPUT_FILEPATH.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "엑셀 파일이 아직 생성되지 않았습니다."},
        )

    # 날짜 필터링 범위가 존재할 경우
    if start_date or end_date:
        logger.info(f"필터링된 엑셀 다운로드 요청: {start_date} ~ {end_date}")
        temp_path = excel.create_temp_filtered_excel(start_date=start_date, end_date=end_date)
        if temp_path and temp_path.exists():
            background_tasks.add_task(remove_file, str(temp_path))
            return FileResponse(
                path=str(temp_path),
                filename=temp_path.name,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "해당 날짜 범위에 기사가 없거나 임시 엑셀 생성에 실패했습니다."},
            )

    return FileResponse(
        path=str(OUTPUT_FILEPATH),
        filename=OUTPUT_FILEPATH.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/api/session")
async def get_session_status():
    """로그인 세션 상태"""
    return {
        "session_file_exists": AUTH_STATE_FILEPATH.exists(),
        "session_file_path": str(AUTH_STATE_FILEPATH),
    }


@router.get("/api/errors")
async def get_errors(limit: int = 20):
    """에러 로그 조회"""
    excel = ExcelManager()
    errors = excel.get_error_logs(limit=limit)
    return {"errors": errors, "count": len(errors)}


@router.get("/api/logs")
async def get_logs(limit: int = 10):
    """실행 로그 조회"""
    excel = ExcelManager()
    logs = excel.get_run_logs(limit=limit)
    return {"logs": logs, "count": len(logs)}


@router.post("/api/session/upload")
async def upload_session_file(file: UploadFile):
    """storage_state.json 세션 파일을 직접 업로드하여 세션을 갱신한다 (클라우드 배포용)."""
    try:
        content = await file.read()
        import json
        data = json.loads(content.decode("utf-8"))
        if "cookies" not in data:
            return JSONResponse(status_code=400, content={"error": "유효하지 않은 storage_state 파일 형식입니다."})
        
        # 파일 저장
        AUTH_STATE_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTH_STATE_FILEPATH, "w", encoding="utf-8") as f:
            f.write(content.decode("utf-8"))
        
        logger.info("대시보드를 통한 세션 상태 파일 업로드 완료")
        return {"status": "success", "message": "세션 상태 파일 업로드 완료!"}
    except Exception as e:
        logger.error(f"세션 파일 업로드 실패: {e}")
        return JSONResponse(status_code=500, content={"error": f"세션 업로드 실패: {str(e)}"})
