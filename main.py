#!/usr/bin/env python3
"""
LLM 기반 일일 자동매매 봇
========================
"""
import argparse
import threading
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.logger import get_logger
from src.utils.config import SCHEDULE_CONFIG
from src.utils.state import state
from src.scheduler.routines import run_morning_routine, run_evening_routine
from src.trading.momentum import check_momentum_and_scalp, sell_all_scalps

logger = get_logger("main")
scheduler = BlockingScheduler(timezone='Asia/Seoul')  # Global scheduler instance with Korea timezone

def run_scheduler():
    """스케줄러 모드 실행"""
    logger.info("=" * 60)
    logger.info("🤖 LLM 자동매매 봇 스케줄러 시작")
    logger.info(f"기본 모드: {state.get_mode().upper()}")
    logger.info("=" * 60)
    
    # 1. 아침 루틴 (한국장 08:00)
    scheduler.add_job(
        lambda: asyncio_run(run_morning_routine(scheduler)), # Pass scheduler for dynamic job addition
        CronTrigger(hour=8, minute=0, day_of_week='mon-fri'),
        id='morning_routine',
        name='아침 루틴 (KR)'
    )

    # 2. 저녁 루틴 (미국장 22:00)
    scheduler.add_job(
        lambda: asyncio_run(run_evening_routine(scheduler)),
        CronTrigger(hour=22, minute=0, day_of_week='mon-fri'),
        id='evening_routine',
        name='저녁 루틴 (US)'
    )

    # 3. 급등주 단타 감시 (09:00 ~ 15:00, 10분 간격)
    scheduler.add_job(
        check_momentum_and_scalp,
        CronTrigger(hour='9-14', minute='*/10', day_of_week='mon-fri'),
        id='momentum_check',
        name='급등주 감시'
    )
    
    # 4. 단타 일괄 청산 (15:20)
    scheduler.add_job(
        sell_all_scalps,
        CronTrigger(hour=15, minute=20, day_of_week='mon-fri'),
        id='scalp_cleanup',
        name='단타 청산'
    )
    
    logger.info("📅 스케줄 등록 완료:")
    logger.info(" - 08:00 : 아침 루틴 (KR 추천/예약)")
    logger.info(" - 09:00~15:00 (10분) : 급등주 감시")
    logger.info(" - 15:20 : 단타 청산")
    logger.info(" - 22:00 : 저녁 루틴 (US 추천)")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")
        scheduler.shutdown()

def asyncio_run(coro):
    """APScheduler에서 async 함수 실행을 위한 래퍼"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)

def run_discord_bot_thread():
    """Discord 봇을 별도 스레드에서 실행"""
    from src.utils.discord_bot import run_discord_bot
    
    thread = threading.Thread(target=run_discord_bot, daemon=True)
    thread.start()
    return thread

def main():
    parser = argparse.ArgumentParser(description="LLM 기반 자동매매 봇")
    parser.add_argument("--discord-bot", action="store_true", help="Discord 봇 모드")
    parser.add_argument("--with-discord", action="store_true", help="스케줄러 + Discord 봇")
    parser.add_argument("--mode", choices=["real", "paper"], default="real", help="실행 모드 (기본: real)")
    parser.add_argument("--account", type=str, default=None, help="사용할 계좌번호 (real 모드, 예: 69247414)")

    # 수동 루틴 실행
    parser.add_argument("--morning", action="store_true", help="아침 루틴 즉시 실행 (KR)")
    parser.add_argument("--evening", action="store_true", help="저녁 루틴 즉시 실행 (US)")

    # CLI Manual Actions (Optional)
    parser.add_argument("--action", choices=["price", "buy", "sell"], help="수동 작업")
    parser.add_argument("--code", type=str)
    parser.add_argument("--qty", type=int, default=1)
    
    args = parser.parse_args()

    # 초기 모드 설정
    state.set_mode(args.mode)
    
    # 계좌 설정 (real 모드 + --account 옵션)
    if args.account and args.mode == "real":
        if not state.set_real_account(args.account):
            from src.utils.config import REAL_ACCOUNTS
            available = ", ".join([f"{a['id']}({a['account_number']})" for a in REAL_ACCOUNTS])
            logger.error(f"계좌번호 '{args.account}'을 찾을 수 없습니다. 사용 가능: {available}")
            return
        logger.info(f"📋 선택된 계좌: {args.account}")
    
    # 수동 루틴 실행
    if args.morning:
        import asyncio
        logger.info("🌅 아침 루틴 수동 실행")
        asyncio.run(run_morning_routine(None))
        return
    
    if args.evening:
        import asyncio
        logger.info("🌙 저녁 루틴 수동 실행")
        asyncio.run(run_evening_routine(None))
        return

    if args.action:
        # CLI 모드 복구
        if not args.code:
            logger.error("종목코드를 입력해주세요 (--code)")
            return

        from src.trading import get_kis_client
        client = get_kis_client(args.mode)

        try:
            if args.action == "price":
                # 시세 조회 (간단 구현)
                # 한국 주식인지 미국 주식인지 코드 길이로 단순 판단
                if len(args.code) == 6 and args.code.isdigit():
                    resp = client.get_price(args.code)
                    output = resp.get("output", {})
                    price = int(output.get("stck_prpr", 0))
                    change = int(output.get("prdy_vrss", 0))
                    rate = float(output.get("prdy_ctrt", 0.0))
                    print(f"\n📊 {args.code} (KR) 현재가 조회")
                    print(f"💰 현재가: {price:,}원")
                    print(f"📈 등락: {change:,}원 ({rate}%)")
                else:
                    # 해외 주식 (임시 NAS)
                    resp = client.get_overseas_price("NAS", args.code)
                    output = resp.get("output", {})
                    price = float(output.get("last", 0))
                    print(f"\n🇺🇸 {args.code} (US) 현재가 조회")
                    print(f"💰 현재가: ${price:,.2f}")

                print("-" * 30)

            elif args.action == "buy":
                print(f"\n💰 매수 주문 실행: {args.code} {args.qty}주")
                resp = client.buy_stock(args.code, args.qty)
                print("✅ 주문 전송 완료")
                print(f"주문번호: {resp.get('output', {}).get('ODNO', 'Unknown')}")

            elif args.action == "sell":
                print(f"\n💸 매도 주문 실행: {args.code} {args.qty}주")
                resp = client.sell_stock(args.code, args.qty)
                print("✅ 주문 전송 완료")
                print(f"주문번호: {resp.get('output', {}).get('ODNO', 'Unknown')}")

        except Exception as e:
            logger.error(f"작업 실패: {e}")

    elif args.discord_bot:
        run_discord_bot_thread().join() # 메인 스레드 유지
        
    else:
        # 스케줄러 모드 (기본)
        if args.with_discord:
            run_discord_bot_thread()
        
        run_scheduler()


if __name__ == "__main__":
    main()
