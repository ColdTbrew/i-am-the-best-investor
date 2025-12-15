"""정기 매매 루틴 (아침/저녁)"""
import asyncio
from datetime import datetime, timedelta

from src.utils.logger import get_logger
from src.utils.state import state
from src.trading import get_kis_client
from src.analysis import analyze_stock, get_daily_recommendations
from src.data import fetch_news, get_market_data, stock_search
from src.utils.discord_bot import send_webhook_message

logger = get_logger(__name__)

async def run_morning_routine(scheduler=None):
    """아침 루틴 (한국장 08:00)"""
    logger.info("🌅 아침 루틴 시작 (한국장)")

    mode = state.get_mode()
    client = get_kis_client(mode)

    # 1. 한국 주식 추천 및 매수 예약
    try:
        market_data = get_market_data()
        news_data = fetch_news(max_items=20)

        # LLM 추천
        recommendations = get_daily_recommendations(market_data, news_data, market="KR")

        embeds = []
        orders_to_schedule = []

        # 예산 계산 (총 예수금의 50%를 3분할)
        balance = None
        try:
            balance = client.get_balance()
            output2 = balance.get("output2", [{}])[0]
            cash = int(output2.get("dnca_tot_amt", 0))
            budget_per_stock = int((cash * 0.5) / 3)
            # 최소 10만원은 되어야 함
            if budget_per_stock < 100000:
                budget_per_stock = 100000
        except Exception as e:
            logger.warning(f"잔고 조회 실패, 기본 예산 사용: {e}")
            budget_per_stock = 100000

        for rec in recommendations[:3]:
            embed = {
                "title": f"🌅 오늘의 추천 (KR): {rec.stock_name}",
                "description": rec.reason,
                "fields": [
                    {"name": "코드", "value": rec.stock_code, "inline": True},
                    {"name": "현재가", "value": f"{rec.current_price:,}원", "inline": True},
                    {"name": "확신도", "value": f"{rec.confidence}/10", "inline": True}
                ],
                "color": 0x00FF00
            }
            embeds.append(embed)

            if rec.current_price > 0:
                qty = int(budget_per_stock / rec.current_price)
                if qty > 0:
                    orders_to_schedule.append({
                        "code": rec.stock_code,
                        "qty": qty,
                        "name": rec.stock_name,
                        "price": 0 # 시장가
                    })

        send_webhook_message("🌅 **오늘의 한국 주식 추천 (매수 예약)**", embeds=embeds)

        # 09:00 매수 실행 예약
        if scheduler and orders_to_schedule:
            run_date = datetime.now().replace(hour=9, minute=0, second=5)
            if run_date < datetime.now():
                 run_date = datetime.now() + timedelta(seconds=10)

            scheduler.add_job(
                execute_buy_orders,
                'date',
                run_date=run_date,
                args=[orders_to_schedule, "KR"],
                name='Morning Buy Orders'
            )
            send_webhook_message(f"⏰ **KR 매수 주문 예약됨**: 09:00 실행 예정 ({len(orders_to_schedule)}종목)")

        # 2. 매도 추천 (보유 중) - balance가 있을 때만
        if balance:
            holdings = balance.get("output1", [])
            sell_candidates = []
            for item in holdings:
                profit_rate = float(item.get("evlu_pfls_rt", 0))
                if profit_rate > 5.0 or profit_rate < -3.0:
                    sell_candidates.append(item)

            if sell_candidates:
                sell_embeds = []
                for item in sell_candidates:
                    sell_embeds.append({
                        "title": f"📉 매도 추천 (KR): {item['prdt_name']}",
                        "description": f"수익률: {float(item['evlu_pfls_rt']):.2f}%",
                        "color": 0xFF0000
                    })
                send_webhook_message("📉 **오늘의 매도 추천 (보유 중)**", embeds=sell_embeds)

    except Exception as e:
        logger.error(f"아침 루틴 실패: {e}")
        send_webhook_message(f"❌ 아침 루틴 에러: {e}")

async def run_evening_routine(scheduler=None):
    """저녁 루틴 (미국장 22:00)"""
    logger.info("🌃 저녁 루틴 시작 (미국장)")
    mode = state.get_mode()
    client = get_kis_client(mode)

    try:
        # 1. 미국 주식 추천
        news_data = fetch_news(max_items=20)
        recommendations = get_daily_recommendations(None, news_data, market="US")

        embeds = []
        orders_to_schedule = []

        # 미국장 예산 (단순 $500/종목)
        budget_usd = 500

        for rec in recommendations[:3]:
            # 거래소 확인 (종목검색 모듈 사용)
            stock_info = stock_search.search_stock(rec.stock_code)
            exchange = stock_info.get("exchange", "NAS") if stock_info else "NAS"

            embed = {
                "title": f"🌃 오늘의 추천 (US): {rec.stock_name}",
                "description": rec.reason,
                "fields": [
                    {"name": "티커", "value": rec.stock_code, "inline": True},
                    {"name": "현재가", "value": f"${rec.current_price:,.2f}", "inline": True},
                    {"name": "거래소", "value": exchange, "inline": True}
                ],
                "color": 0x0000FF
            }
            embeds.append(embed)

            if rec.current_price > 0:
                qty = int(budget_usd / rec.current_price)
                if qty > 0:
                    orders_to_schedule.append({
                        "code": rec.stock_code,
                        "qty": qty,
                        "name": rec.stock_name,
                        "exchange": exchange,
                        "price": rec.current_price # 지정가 (미국장은 시장가 제한 있을 수 있음)
                    })

        send_webhook_message("🌃 **오늘의 미국 주식 추천**", embeds=embeds)

        # 23:30 매수 실행 예약
        if scheduler and orders_to_schedule:
             run_date = datetime.now().replace(hour=23, minute=30, second=0)
             if run_date < datetime.now():
                  run_date = datetime.now() + timedelta(seconds=10)

             scheduler.add_job(
                execute_buy_orders,
                'date',
                run_date=run_date,
                args=[orders_to_schedule, "US"],
                name='Evening Buy Orders'
            )
             send_webhook_message(f"⏰ **US 매수 주문 예약됨**: 23:30 실행 예정")

        # 2. 매도 추천 (미국 보유 종목)
        try:
            # 해외 잔고 조회
            ovs_balance = client.get_overseas_balance()
            holdings = ovs_balance.get("output1", [])

            sell_candidates = []
            for item in holdings:
                profit_rate = float(item.get("evlu_pfls_rt", 0))
                # 미국장은 변동성이 크므로 기준을 좀 더 넓게 잡거나 동일하게
                if profit_rate > 5.0 or profit_rate < -3.0:
                    sell_candidates.append(item)

            if sell_candidates:
                sell_embeds = []
                for item in sell_candidates:
                    sell_embeds.append({
                        "title": f"📉 매도 추천 (US): {item['ovrs_pdno']}",
                        "description": f"수익률: {float(item['evlu_pfls_rt']):.2f}%",
                        "color": 0xFF0000
                    })
                send_webhook_message("📉 **오늘의 매도 추천 (미국 보유)**", embeds=sell_embeds)

        except Exception as e:
            logger.warning(f"미국 잔고 조회 실패: {e}")

    except Exception as e:
        logger.error(f"저녁 루틴 실패: {e}")
        send_webhook_message(f"❌ 저녁 루틴 에러: {e}")

def execute_buy_orders(orders: list, market: str):
    """예약된 매수 주문 실행"""
    logger.info(f"🚀 예약 매수 주문 실행 ({market}): {len(orders)}건")

    mode = state.get_mode()
    client = get_kis_client(mode)

    for order in orders:
        try:
            code = order["code"]
            qty = order["qty"]
            name = order["name"]

            if market == "KR":
                res = client.buy_stock(code, qty, price=0) # 시장가
            else:
                # US
                exchange = order.get("exchange", "NAS")
                price = order.get("price", 0)
                res = client.buy_overseas_stock(exchange, code, qty, price)

            if res.get("rt_cd") == "0":
                send_webhook_message(f"✅ **예약 매수 체결 ({market})**\n{name} ({code}) {qty}주")
            else:
                send_webhook_message(f"❌ **예약 매수 실패 ({name})**: {res.get('msg1')}")

        except Exception as e:
            logger.error(f"주문 실행 중 에러: {e}")
