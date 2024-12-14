"""LLM 기반 투자 분석 엔진"""
import json
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from src.utils.config import OPENAI_API_KEY, OPENAI_MODEL
from src.utils.logger import get_logger

logger = get_logger(__name__)

# OpenAI 클라이언트
client = OpenAI(api_key=OPENAI_API_KEY)


@dataclass
class TradeDecision:
    """매매 결정 결과"""
    action: str  # "buy", "sell", "hold"
    stock_code: str
    stock_name: str
    quantity: int
    price: int  # 0이면 시장가
    reason: str  # 판단 이유
    confidence: int  # 1-10 확신도


def analyze_for_buy(market_data: dict, news_data: list, budget: int) -> list[TradeDecision]:
    """
    매수 분석: 시장 데이터와 뉴스를 기반으로 매수할 종목 추천
    
    Args:
        market_data: 시장 데이터 (종목별 현재가, 등락률 등)
        news_data: 최신 뉴스 리스트
        budget: 투자 가능 금액
    
    Returns:
        매수 추천 종목 리스트
    """
    from src.utils.config import RISK_CONFIG
    
    min_buy = RISK_CONFIG.get("min_buy_amount", 100000)
    max_buy = RISK_CONFIG.get("max_buy_amount", 5000000)
    default_buy = RISK_CONFIG.get("buy_amount_per_stock", 1000000)
    
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 현재 시장 데이터
{json.dumps(market_data, ensure_ascii=False, indent=2)}

## 최신 뉴스
{json.dumps(news_data, ensure_ascii=False, indent=2)}

## 투자 조건
- 투자 가능 금액: {budget:,}원
- 종목당 기본 매수금액: {default_buy:,}원
- 최소 매수금액: {min_buy:,}원
- 최대 매수금액: {max_buy:,}원

## 분석 요청
위 정보를 바탕으로 오늘 매수하기 좋은 종목을 최대 3개까지 추천해주세요.
확신도가 높은 종목은 최대 {max_buy:,}원까지, 낮은 종목은 {min_buy:,}원 정도로 추천하세요.

각 종목에 대해 다음 정보를 JSON 배열로 응답해주세요:
- action: "buy"
- stock_code: 종목코드 (6자리)
- stock_name: 종목명
- quantity: 추천 매수 수량 (현재가 기준 계산)
- price: 추천 매수가 (0이면 시장가)
- reason: 매수 추천 이유 (2-3문장)
- confidence: 확신도 (1-10)

매수할 종목이 없으면 빈 배열 []을 반환하세요.

JSON 배열만 응답하세요. 다른 텍스트 없이 JSON만."""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # 결과가 배열이 아닌 경우 처리
        if isinstance(result, dict):
            result = result.get("recommendations", result.get("stocks", []))
        
        decisions = []
        for item in result:
            confidence = item.get("confidence", 5)
            price = item.get("price", 0)
            
            # 확신도 기반 매수 금액 계산
            buy_amount = calculate_buy_amount(confidence, min_buy, max_buy, default_buy)
            
            # 수량 계산 (가격이 있으면 계산, 없으면 LLM 추천 수량 사용)
            if price > 0:
                quantity = max(1, int(buy_amount / price))
            else:
                quantity = item.get("quantity", 1)
            
            decisions.append(TradeDecision(
                action="buy",
                stock_code=item.get("stock_code", ""),
                stock_name=item.get("stock_name", ""),
                quantity=quantity,
                price=price,
                reason=item.get("reason", ""),
                confidence=confidence,
            ))
        
        logger.info(f"매수 분석 완료: {len(decisions)}개 종목 추천")
        return decisions
        
    except Exception as e:
        logger.error(f"매수 분석 실패: {e}")
        return []


def calculate_buy_amount(confidence: int, min_amount: int, max_amount: int, default_amount: int) -> int:
    """
    확신도 기반 매수 금액 계산
    
    확신도 9-10: 최대 금액 (500만원)
    확신도 7-8:  기본 금액 + α
    확신도 5-6:  기본 금액 (100만원)
    확신도 3-4:  최소 금액 (10만원)
    확신도 1-2:  매수 안함 수준
    
    Args:
        confidence: 확신도 (1-10)
        min_amount: 최소 금액
        max_amount: 최대 금액
        default_amount: 기본 금액
    
    Returns:
        매수 금액
    """
    if confidence >= 9:
        return max_amount  # 500만원
    elif confidence >= 7:
        # 기본 ~ 최대 사이 (200 ~ 400만원)
        return int(default_amount + (max_amount - default_amount) * (confidence - 6) / 4)
    elif confidence >= 5:
        return default_amount  # 100만원
    elif confidence >= 3:
        # 최소 ~ 기본 사이 (10 ~ 50만원)
        return int(min_amount + (default_amount - min_amount) * (confidence - 2) / 3)
    else:
        return min_amount  # 10만원


def analyze_for_sell(portfolio: list[dict], news_data: list) -> list[TradeDecision]:
    """
    매도 분석: 보유 종목을 평가하여 매도할 종목 결정
    
    Args:
        portfolio: 보유 종목 리스트 (종목코드, 종목명, 매수가, 현재가, 수익률, 수량)
        news_data: 최신 뉴스 리스트
    
    Returns:
        매도 결정 종목 리스트
    """
    if not portfolio:
        logger.info("보유 종목 없음, 매도 분석 스킵")
        return []
    
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 현재 보유 종목
{json.dumps(portfolio, ensure_ascii=False, indent=2)}

## 최신 뉴스
{json.dumps(news_data, ensure_ascii=False, indent=2)}

## 매도 기준
- 손절: 수익률 -5% 이하
- 익절: 수익률 +15% 이상
- 또는 뉴스/시장 상황에 따른 판단

## 분석 요청
각 보유 종목에 대해 매도 여부를 결정해주세요.

매도할 종목에 대해서만 다음 정보를 JSON 배열로 응답해주세요:
- action: "sell"
- stock_code: 종목코드
- stock_name: 종목명
- quantity: 매도 수량 (전량 매도 추천)
- price: 매도가 (0이면 시장가, 지정가 가능)
- reason: 매도 이유 (2-3문장, 익절/손절/기타 명시)
- confidence: 확신도 (1-10)

매도할 종목이 없으면 빈 배열 []을 반환하세요.

JSON 배열만 응답하세요. 다른 텍스트 없이 JSON만."""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if isinstance(result, dict):
            result = result.get("recommendations", result.get("stocks", []))
        
        decisions = []
        for item in result:
            decisions.append(TradeDecision(
                action="sell",
                stock_code=item.get("stock_code", ""),
                stock_name=item.get("stock_name", ""),
                quantity=item.get("quantity", 0),
                price=item.get("price", 0),
                reason=item.get("reason", ""),
                confidence=item.get("confidence", 5),
            ))
        
        logger.info(f"매도 분석 완료: {len(decisions)}개 종목 매도 추천")
        return decisions
        
    except Exception as e:
        logger.error(f"매도 분석 실패: {e}")
        return []


def analyze_stock(stock_code: str, stock_name: str, current_price: int, 
                  news: list = None) -> str:
    """
    개별 종목 분석 (Discord 명령어용)
    
    Args:
        stock_code: 종목코드
        stock_name: 종목명
        current_price: 현재가
        news: 관련 뉴스
    
    Returns:
        분석 결과 텍스트
    """
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 분석 대상
- 종목코드: {stock_code}
- 종목명: {stock_name}
- 현재가: {current_price:,}원

## 관련 뉴스
{json.dumps(news or [], ensure_ascii=False, indent=2)}

## 분석 요청
이 종목에 대해 간단히 분석해주세요:
1. 현재 투자 매력도 (상/중/하)
2. 단기 전망 (1-2주)
3. 매수/매도/관망 추천
4. 주요 근거

3-4문장으로 간결하게 답변해주세요."""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"종목 분석 실패: {e}")
        return f"종목 분석 중 오류가 발생했습니다: {e}"


@dataclass
class StockRecommendation:
    """추천 종목 정보"""
    stock_code: str
    stock_name: str
    current_price: int
    change: int
    change_rate: float
    reason: str
    confidence: int


def get_daily_recommendations(market_data: dict, news_data: list) -> list[StockRecommendation]:
    """
    LLM 기반 금일 추천 종목 3개 조회
    
    Args:
        market_data: 시장 데이터
        news_data: 뉴스 데이터
    
    Returns:
        추천 종목 리스트 (최대 3개)
    """
    from src.trading import get_kis_client
    
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 현재 시장 데이터
{json.dumps(market_data, ensure_ascii=False, indent=2)}

## 최신 뉴스
{json.dumps(news_data[:10], ensure_ascii=False, indent=2)}

## 분석 요청
오늘 매수하기 좋은 종목 3개를 추천해주세요.
단기(1-2주) 상승 가능성이 높은 종목을 선정하세요.

각 종목에 대해 다음 정보를 JSON 배열로 응답해주세요:
- stock_code: 종목코드 (6자리)
- stock_name: 종목명
- reason: 추천 이유 (핵심 포인트 2-3문장)
- confidence: 확신도 (1-10)

JSON 배열만 응답하세요. 다른 텍스트 없이 JSON만."""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # 결과가 배열이 아닌 경우 처리
        if isinstance(result, dict):
            result = result.get("recommendations", result.get("stocks", []))
        
        # KIS API로 현재가 조회
        kis_client = get_kis_client()
        recommendations = []
        
        for item in result[:3]:  # 최대 3개
            stock_code = str(item.get("stock_code", "")).strip()
            stock_name = item.get("stock_name", "")
            
            # 종목코드 유효성 검증 (6자리 숫자만)
            if not stock_code.isdigit() or len(stock_code) != 6:
                logger.warning(f"잘못된 종목코드 스킵: {stock_code} ({stock_name})")
                continue
            
            try:
                price_data = kis_client.get_price(stock_code)
                output = price_data.get("output", {})
                
                current_price = int(output.get("stck_prpr", 0))
                change = int(output.get("prdy_vrss", 0))
                change_rate = float(output.get("prdy_ctrt", 0))
                
                recommendations.append(StockRecommendation(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    current_price=current_price,
                    change=change,
                    change_rate=change_rate,
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 5),
                ))
            except Exception as e:
                logger.warning(f"{stock_name} 시세 조회 실패: {e}")
        
        logger.info(f"추천 종목 조회 완료: {len(recommendations)}개")
        return recommendations
        
    except Exception as e:
        logger.error(f"추천 종목 분석 실패: {e}")
        return []

