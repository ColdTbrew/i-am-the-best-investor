"""급등주 단타 전략"""
from datetime import datetime
import time
import json
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.config import RISK_CONFIG
from src.utils.state import state
from src.trading import get_kis_client
from src.utils.discord_bot import send_webhook_message

logger = get_logger(__name__)

# 데이터 파일 경로
STATE_FILE = Path(__file__).parent.parent.parent / "data" / "scalping_state.json"

# 금일 단타 매수 종목 추적 (매도 위해)
scalping_positions = []

def load_state():
    """상태 파일 로드"""
    global scalping_positions
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                # 날짜가 오늘인 것만 로드 (자정 지나면 리셋)
                today = datetime.now().strftime("%Y-%m-%d")
                valid_positions = []
                for pos in data:
                    pos_time = pos.get("time_str", "")
                    if pos_time.startswith(today):
                        valid_positions.append(pos)
                scalping_positions = valid_positions
                logger.info(f"단타 상태 로드: {len(scalping_positions)}건")
        except Exception as e:
            logger.error(f"상태 로드 실패: {e}")

def save_state():
    """상태 파일 저장"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # datetime 객체 직렬화 위해 문자열 변환
        saved_data = []
        for pos in scalping_positions:
            item = pos.copy()
            if isinstance(item.get("time"), datetime):
                item["time_str"] = item["time"].strftime("%Y-%m-%d %H:%M:%S")
                del item["time"]
            saved_data.append(item)

        with open(STATE_FILE, "w") as f:
            json.dump(saved_data, f)
    except Exception as e:
        logger.error(f"상태 저장 실패: {e}")

# 모듈 로드 시 상태 복구
load_state()

def check_momentum_and_scalp():
    """급등주 포착 및 단타 매수"""
    # 09:00 ~ 15:00 사이에만 동작
    now = datetime.now()
    if not (9 <= now.hour < 15):
        return

    try:
        mode = state.get_mode()
        client = get_kis_client(mode)

        # 1. 급등주 조회 (랭킹)
        try:
            rank_data = client.get_rank_rising()
        except Exception as e:
            return

        rising_stocks = rank_data.get("output", [])

        # 2. 필터링 (거래량 동반한 5~15% 급등)
        target = None
        for stock in rising_stocks:
            rate = float(stock.get("prdy_ctrt", 0)) # 등락률
            vol = int(stock.get("acml_vol", 0))    # 거래량
            code = stock["stck_shrn_iscd"]

            # 너무 많이 오른건 위험 (상한가 근처 제외), 거래량 10만주 이상
            if 5.0 <= rate <= 20.0 and vol > 100000:
                # 이미 매수한적 있는지 체크
                already_bought = any(s["code"] == code for s in scalping_positions)
                if already_bought:
                    continue

                target = stock
                break

        if target:
            code = target["stck_shrn_iscd"]
            name = target["hts_kor_isnm"]
            price = int(target["stck_prpr"])

            # 3. 매수 (10만원 어치)
            amount = RISK_CONFIG["scalping_amount"]
            qty = int(amount / price)

            if qty > 0:
                logger.info(f"🚀 급등주 포착! 매수 시도: {name} ({code}) {qty}주")
                res = client.buy_stock(code, qty) # 시장가

                if res.get("rt_cd") == "0":
                    scalping_positions.append({
                        "code": code,
                        "name": name,
                        "qty": qty,
                        "buy_price": price,
                        "time": now,
                        "time_str": now.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_state()

                    send_webhook_message(f"🚀 **급등주 단타 진입**\n{name} ({code}) {qty}주 @ {price:,}원 (등락률: {target['prdy_ctrt']}%)")

    except Exception as e:
        logger.error(f"단타 로직 에러: {e}")

def sell_all_scalps():
    """단타 종목 일괄 매도 (장 마감 전)"""
    if not scalping_positions:
        return

    logger.info(f"🏁 단타 종목 일괄 청산 ({len(scalping_positions)}개)")

    try:
        mode = state.get_mode()
        client = get_kis_client(mode)

        for pos in scalping_positions:
            res = client.sell_stock(pos["code"], pos["qty"])
            if res.get("rt_cd") == "0":
                send_webhook_message(f"🏁 **단타 청산**\n{pos['name']} {pos['qty']}주 매도 주문")
            else:
                send_webhook_message(f"⚠️ **단타 청산 실패**\n{pos['name']}: {res.get('msg1')}")

        scalping_positions.clear()
        save_state() # 비우고 저장

    except Exception as e:
        logger.error(f"일괄 매도 실패: {e}")
