"""일일 자동매매 작업"""
from datetime import datetime
from typing import Optional

from src.utils.logger import get_logger
from src.utils.discord_bot import (
    notify_system_start,
    notify_trade_executed,
    notify_daily_report,
    notify_error,
    notify_news_summary,
)
from src.utils.config import RISK_CONFIG
from src.utils.state import state
from src.trading import get_kis_client
from src.analysis import analyze_for_buy, analyze_for_sell, TradeDecision
from src.data import fetch_news, get_market_data as get_stock_data

logger = get_logger(__name__)


class DailyTradingJob:
    """일일 자동매매 작업"""
    
    def __init__(self):
        self.kis_client = get_kis_client()
        self.is_stopped = False  # 거래 중지 플래그
    
    def run(self):
        """일일 매매 작업 실행"""
        logger.info("=" * 50)
        logger.info("일일 자동매매 작업 시작")
        logger.info(f"거래 모드: {state.get_mode()}")
        logger.info("=" * 50)
        
        # 시스템 시작 알림
        notify_system_start()
        
        try:
            # 1. 데이터 수집
            logger.info("📊 데이터 수집 시작")
            portfolio = self._get_portfolio()
            market_data = self._get_market_data()
            news_data = self._get_news()
            budget = self._get_available_budget()
            
            logger.info(f"보유 종목: {len(portfolio)}개")
            logger.info(f"투자 가능 금액: {budget:,}원")
            logger.info(f"수집된 뉴스: {len(news_data)}개")
            
            # 1.5. 뉴스 및 시장 브리핑 알림
            notify_news_summary(news_data, market_data)
            
            # 2. 매도 분석 및 실행 (먼저 매도하여 현금 확보)
            logger.info("📉 매도 분석 시작")
            sell_decisions = analyze_for_sell(portfolio, news_data)
            
            for decision in sell_decisions:
                if self.is_stopped:
                    logger.info("거래 중지됨, 매도 스킵")
                    break
                self._execute_trade(decision)
            
            # 3. 매수 분석 및 실행
            logger.info("📈 매수 분석 시작")
            buy_decisions = analyze_for_buy(market_data, news_data, budget)
            
            # 최대 매수 종목 수 제한
            max_buy = RISK_CONFIG["max_buy_per_day"]
            buy_decisions = buy_decisions[:max_buy]
            
            for decision in buy_decisions:
                if self.is_stopped:
                    logger.info("거래 중지됨, 매수 스킵")
                    break
                self._execute_trade(decision)
            
            # 4. 일일 리포트 생성
            logger.info("📊 일일 리포트 생성")
            self._send_daily_report()
            
            logger.info("일일 자동매매 작업 완료")
            
        except Exception as e:
            error_msg = f"일일 작업 실패: {e}"
            logger.error(error_msg)
            notify_error(error_msg)
    
    def _get_portfolio(self) -> list[dict]:
        """보유 종목 조회"""
        try:
            result = self.kis_client.get_balance()
            portfolio = []
            
            for item in result.get("output1", []):
                portfolio.append({
                    "stock_code": item.get("pdno", ""),
                    "name": item.get("prdt_name", ""),
                    "quantity": int(item.get("hldg_qty", 0)),
                    "buy_price": int(item.get("pchs_avg_pric", 0)),
                    "current_price": int(item.get("prpr", 0)),
                    "profit_rate": float(item.get("evlu_pfls_rt", 0)),
                    "profit_amount": int(item.get("evlu_pfls_amt", 0)),
                })
            
            return portfolio
            
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return []
    
    def _get_market_data(self) -> dict:
        """시장 데이터 조회 (관심 종목)"""
        try:
            return get_stock_data()
        except Exception as e:
            logger.warning(f"시장 데이터 수집 실패: {e}")
            return {"stocks": [], "top_gainers": [], "top_losers": []}
    
    def _get_news(self) -> list:
        """뉴스 데이터 수집"""
        try:
            return fetch_news(max_items=15)
        except Exception as e:
            logger.warning(f"뉴스 수집 실패: {e}")
            return []
    
    def _get_available_budget(self) -> int:
        """투자 가능 금액 조회"""
        try:
            result = self.kis_client.get_balance()
            # 주문 가능 현금
            return int(result.get("output2", [{}])[0].get("dnca_tot_amt", 0))
        except:
            return 0
    
    def _execute_trade(self, decision: TradeDecision):
        """매매 실행"""
        logger.info(f"매매 실행: {decision.action} {decision.stock_name}")
        
        try:
            if decision.action == "buy":
                result = self.kis_client.buy_stock(
                    decision.stock_code,
                    decision.quantity,
                    decision.price,
                )
            else:  # sell
                result = self.kis_client.sell_stock(
                    decision.stock_code,
                    decision.quantity,
                    decision.price,
                )
            
            success = result.get("rt_cd") == "0"
            notify_trade_executed(decision, success, result)
            
            if success:
                logger.info(f"주문 성공: {decision.stock_code}")
            else:
                logger.warning(f"주문 실패: {result.get('msg1', '')}")
                
        except Exception as e:
            logger.error(f"주문 실행 실패: {e}")
            notify_trade_executed(decision, False)
    
    def _send_daily_report(self):
        """일일 리포트 발송"""
        try:
            portfolio = self._get_portfolio()
            result = self.kis_client.get_balance()
            
            # 총 평가금액
            output2 = result.get("output2", [{}])[0]
            total_value = int(output2.get("tot_evlu_amt", 0))
            
            # 일일 손익 (간단 계산)
            daily_profit = sum(p["profit_amount"] for p in portfolio)
            daily_profit_rate = (daily_profit / total_value * 100) if total_value > 0 else 0
            
            # 포트폴리오 요약
            portfolio_summary = [
                {"name": p["name"], "profit_rate": p["profit_rate"]}
                for p in portfolio
            ]
            
            notify_daily_report(
                portfolio_summary,
                total_value,
                daily_profit,
                daily_profit_rate,
            )
            
        except Exception as e:
            logger.error(f"일일 리포트 생성 실패: {e}")
    
    def stop_trading(self):
        """거래 중지"""
        self.is_stopped = True
        logger.info("거래 중지됨")
    
    def resume_trading(self):
        """거래 재개"""
        self.is_stopped = False
        logger.info("거래 재개됨")
