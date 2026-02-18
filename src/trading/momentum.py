"""급등주 단타 전략"""
from datetime import datetime
import asyncio
import time
import json
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.config import RISK_CONFIG
from src.utils.state import state
from src.trading import get_kis_client
from src.utils.discord_bot import send_webhook_message, send_momentum_approval

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


async def check_momentum_and_scalp():
    """급등주 포착 및 단타 매수 승인 요청"""
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
            logger.error(f"급등주 랭킹 조회 실패: {e}")
            return

        rising_stocks = rank_data.get("output", [])

        # 2. 필터링 (거래량 동반한 5~20% 급등)
        target = None
        for stock in rising_stocks:
            rate = float(stock.get("prdy_ctrt", 0))  # 등락률
            vol = int(stock.get("acml_vol", 0))       # 거래량
            code = stock["stck_shrn_iscd"]

            # 너무 많이 오른건 위험 (상한가 근처 제외), 거래량 10만주 이상
            if 5.0 <= rate <= 20.0 and vol > 100000:
                # 이미 매수한적 있는지 체크
                already_bought = any(s["code"] == code for s in scalping_positions)
                if already_bought:
                    logger.info(f"이미 매수한 종목 스킵: {code}")
                    continue

                target = stock
                break

        if not target:
            return

        code = target["stck_shrn_iscd"]
        name = target["hts_kor_isnm"]
        price = int(target["stck_prpr"])
        rate = float(target["prdy_ctrt"])

        # 3. 잔액 조회 및 예산/수량 계산
        amount = RISK_CONFIG.get("scalping_amount", 100000)

        try:
            balance = client.get_balance()
            output2 = balance.get("output2", [{}])[0]
            cash = int(output2.get("dnca_tot_amt", 0))
            logger.info(f"현재 예수금: {cash:,}원 / 단타 예산: {amount:,}원")

            if cash < amount:
                msg = (
                    f"⚠️ **단타 매수 불가 — 잔액 부족**\n"
                    f"종목: {name} ({code}) | 등락률: {rate:+.1f}%\n"
                    f"필요 금액: {amount:,}원 | 현재 예수금: {cash:,}원"
                )
                logger.warning(f"잔액 부족으로 단타 매수 불가: 필요 {amount:,}원, 보유 {cash:,}원")
                send_webhook_message(msg)
                return
        except Exception as e:
            logger.warning(f"잔액 조회 실패 (기본 예산으로 진행): {e}")
            send_webhook_message(f"⚠️ 잔액 조회 실패, 단타 매수 승인 요청 취소: {e}")
            return

        qty = int(amount / price)
        if qty <= 0:
            msg = (
                f"⚠️ **단타 매수 불가 — 수량 부족**\n"
                f"종목: {name} ({code}) | 현재가: {price:,}원\n"
                f"예산 {amount:,}원으로 1주도 매수 불가 (주가가 예산 초과)"
            )
            logger.warning(f"수량 부족으로 단타 매수 불가: 예산 {amount:,}원, 현재가 {price:,}원")
            send_webhook_message(msg)
            return

        # 4. 디스코드 승인 요청
        logger.info(f"🚀 급등주 포착! 승인 요청: {name} ({code}) {qty}주 @ {price:,}원 (등락률: {rate:+.1f}%)")
        await send_momentum_approval(code, name, qty, price, rate)

    except Exception as e:
        logger.error(f"단타 로직 에러: {e}")


def execute_momentum_buy(code: str, name: str, qty: int, price: int) -> dict:
    """승인 후 실제 단타 매수 실행 (동기 함수, 버튼 콜백에서 thread로 호출)"""
    now = datetime.now()
    mode = state.get_mode()
    client = get_kis_client(mode)

    logger.info(f"🛒 단타 매수 실행: {name} ({code}) {qty}주 @ {price:,}원")

    try:
        # 잔액 재확인
        balance = client.get_balance()
        output2 = balance.get("output2", [{}])[0]
        cash = int(output2.get("dnca_tot_amt", 0))
        needed = price * qty
        if cash < needed:
            msg = f"잔액 부족: 필요 {needed:,}원, 현재 예수금 {cash:,}원"
            logger.warning(f"매수 실행 취소 — {msg}")
            return {"rt_cd": "1", "msg1": msg}
    except Exception as e:
        logger.warning(f"매수 실행 전 잔액 재확인 실패: {e}")

    res = client.buy_stock(code, qty)  # 시장가

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
        logger.info(f"✅ 단타 매수 체결: {name} ({code}) {qty}주")
        send_webhook_message(
            f"✅ **단타 매수 체결**\n{name} ({code}) {qty}주 @ {price:,}원"
        )
    else:
        err = res.get("msg1", "알 수 없는 오류")
        logger.error(f"❌ 단타 매수 실패: {name} ({code}) — {err}")
        send_webhook_message(
            f"❌ **단타 매수 실패**\n{name} ({code}) {qty}주\n사유: {err}"
        )

    return res


def sell_all_scalps():
    """단타 종목 일괄 매도 (장 마감 전)"""
    if not scalping_positions:
        return

    logger.info(f"🏁 단타 종목 일괄 청산 ({len(scalping_positions)}개)")

    try:
        mode = state.get_mode()
        client = get_kis_client(mode)

        for pos in scalping_positions:
            try:
                res = client.sell_stock(pos["code"], pos["qty"])
                if res.get("rt_cd") == "0":
                    send_webhook_message(f"🏁 **단타 청산**\n{pos['name']} {pos['qty']}주 매도 주문")
                    logger.info(f"단타 청산 성공: {pos['name']} {pos['qty']}주")
                else:
                    err = res.get("msg1", "알 수 없는 오류")
                    logger.error(f"단타 청산 실패: {pos['name']} — {err}")
                    send_webhook_message(f"⚠️ **단타 청산 실패**\n{pos['name']}: {err}")
            except Exception as e:
                logger.error(f"단타 청산 중 에러: {pos['name']} — {e}")
                send_webhook_message(f"⚠️ **단타 청산 에러**\n{pos['name']}: {e}")

        scalping_positions.clear()
        save_state()  # 비우고 저장

    except Exception as e:
        logger.error(f"일괄 매도 실패: {e}")
