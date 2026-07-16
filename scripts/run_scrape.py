"""
run_scrape.py — CLI 수집 실행 스크립트

cron이나 Task Scheduler에서 호출하거나 수동 실행용.

사용법:
    python scripts/run_scrape.py                   # 오늘 기사 수집
    python scripts/run_scrape.py --date 2026-07-12  # 특정 날짜 수집
    python scripts/run_scrape.py --no-body           # 본문 없이 목록만
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import now_kst, setup_logger
from app.scraper.collector import run_collection
from app.storage.excel_manager import ExcelManager

logger = setup_logger("run_scrape")


async def main(target_date: str = None, fetch_body: bool = True):
    """수집 실행 메인 함수"""
    if target_date is None:
        target_date = now_kst().strftime("%Y-%m-%d")

    print("=" * 60)
    print("  AI 정책 기사 자동 스크랩 실행")
    print(f"  대상 날짜: {target_date}")
    print(f"  본문 수집: {'예' if fetch_body else '아니오'}")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    excel = ExcelManager()

    # 기존 기사 ID 로드 (중복 방지)
    existing_ids = excel.get_existing_article_ids()
    logger.info(f"기존 기사 {len(existing_ids)}건 로드됨 (중복 확인용)")

    # 수집 실행
    result = await run_collection(
        existing_ids=existing_ids,
        target_date=target_date,
        fetch_body=fetch_body,
    )

    # 엑셀 저장
    if result.articles:
        saved = excel.save_articles(result.articles)
        logger.info(f"엑셀 저장 완료: {saved}건")

    # 실행 로그 저장
    excel.save_run_log(
        run_time=result.run_time,
        total_found=result.total_found,
        new_count=result.new_count,
        skipped_count=result.skipped_count,
        error_count=result.error_count,
        elapsed_seconds=result.elapsed_seconds,
    )

    # 에러 로그 저장
    if result.errors:
        excel.save_error_log(result.errors)

    # 결과 출력
    print()
    print("─" * 40)
    print(f"  📊 수집 결과")
    print(f"  발견: {result.total_found}건")
    print(f"  신규: {result.new_count}건")
    print(f"  중복: {result.skipped_count}건")
    print(f"  실패: {result.error_count}건")
    print(f"  소요: {result.elapsed_seconds}초")
    print("─" * 40)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI 정책 기사 자동 스크랩"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="수집 대상 날짜 (YYYY-MM-DD). 기본: 오늘",
    )
    parser.add_argument(
        "--no-body",
        action="store_true",
        help="본문 수집 없이 목록만 수집",
    )

    args = parser.parse_args()
    asyncio.run(main(target_date=args.date, fetch_body=not args.no_body))
