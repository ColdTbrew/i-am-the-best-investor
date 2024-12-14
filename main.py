#!/usr/bin/env python3
"""
LLM 기반 일일 자동매매 봇
========================

매일 장 개장 시간에 자동으로 실행되어:
1. 시장 데이터 및 뉴스 수집
2. LLM이 매수/매도 분석
3. 자동 주문 실행
4. Discord로 결과 알림 (판단 이유 포함)

Usage:
    # 즉시 실행 (테스트용)
    python main.py --run-now
    
    # 스케줄러 모드 (매일 08:30 실행)
    python main.py
    
    # Discord 봇 실행
    python main.py --discord-bot
"""
import argparse
import threading
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.logger import get_logger
from src.utils.config import TRADING_MODE, SCHEDULE_CONFIG
from src.scheduler import DailyTradingJob

logger = get_logger("main")


def run_daily_job():
    """일일 매매 작업 실행"""
    job = DailyTradingJob()
    job.run()


def run_scheduler():
    """스케줄러 모드 실행"""
    logger.info("=" * 60)
    logger.info("🤖 LLM 자동매매 봇 스케줄러 시작")
    logger.info(f"거래 모드: {TRADING_MODE}")
    logger.info(f"실행 시간: 매일 {SCHEDULE_CONFIG['bot_start']}")
    logger.info("=" * 60)
    
    scheduler = BlockingScheduler()
    
    # 매일 08:30에 실행
    hour, minute = SCHEDULE_CONFIG['bot_start'].split(':')
    scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=int(hour), minute=int(minute), day_of_week='mon-fri'),
        id='daily_trading',
        name='일일 자동매매',
    )
    
    logger.info("스케줄러 시작, Ctrl+C로 종료")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")
        scheduler.shutdown()


def run_discord_bot_thread():
    """Discord 봇을 별도 스레드에서 실행"""
    from src.utils.discord_bot import run_discord_bot
    
    thread = threading.Thread(target=run_discord_bot, daemon=True)
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description="LLM 기반 자동매매 봇")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="스케줄러 없이 즉시 실행 (테스트용)",
    )
    parser.add_argument(
        "--discord-bot",
        action="store_true",
        help="Discord 봇 모드로 실행",
    )
    parser.add_argument(
        "--with-discord",
        action="store_true",
        help="Discord 봇과 함께 스케줄러 실행",
    )

    # CLI Manual Actions
    parser.add_argument(
        "--action",
        choices=["price", "buy", "sell"],
        help="수동 작업 실행 (시세 조회, 매수, 매도)",
    )
    parser.add_argument(
        "--code",
        type=str,
        help="종목코드 (6자리)",
    )
    parser.add_argument(
        "--qty",
        type=int,
        default=1,
        help="주문 수량 (기본값: 1)",
    )
    
    args = parser.parse_args()

    if args.action:
        # 수동 작업 모드
        from src.trading.kis_client import get_kis_client

        if not args.code:
            logger.error("종목코드를 입력해주세요 (--code)")
            return

        client = get_kis_client()

        try:
            if args.action == "price":
                # 시세 조회
                resp = client.get_price(args.code)
                output = resp.get("output", {})
                # inquire-price usually returns:
                # stck_prpr (Current Price)
                # prdy_vrss (Change)
                # prdy_ctrt (Change Rate)

                price = int(output.get("stck_prpr", 0))
                change = int(output.get("prdy_vrss", 0))
                rate = float(output.get("prdy_ctrt", 0.0))

                print(f"\n📊 {args.code} 현재가 조회")
                print(f"💰 현재가: {price:,}원")
                print(f"📈 등락: {change:,}원 ({rate}%)")
                print("-" * 30)

            elif args.action == "buy":
                # 매수
                print(f"\n💰 매수 주문 실행: {args.code} {args.qty}주")
                resp = client.buy_stock(args.code, args.qty)
                print("✅ 주문 전송 완료")
                print(f"주문번호: {resp.get('output', {}).get('ODNO', 'Unknown')}")

            elif args.action == "sell":
                # 매도
                print(f"\n💸 매도 주문 실행: {args.code} {args.qty}주")
                resp = client.sell_stock(args.code, args.qty)
                print("✅ 주문 전송 완료")
                print(f"주문번호: {resp.get('output', {}).get('ODNO', 'Unknown')}")

        except Exception as e:
            logger.error(f"작업 실패: {e}")

    elif args.discord_bot:
        # Discord 봇 전용 모드
        logger.info("Discord 봇 모드로 실행")
        from src.utils.discord_bot import run_discord_bot
        run_discord_bot()
        
    elif args.run_now:
        # 즉시 실행 모드 (테스트용)
        logger.info("즉시 실행 모드")
        run_daily_job()
        
    else:
        # 스케줄러 모드
        if args.with_discord:
            logger.info("Discord 봇 스레드 시작")
            run_discord_bot_thread()
        
        run_scheduler()


if __name__ == "__main__":
    main()
