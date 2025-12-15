"""LLM 기반 투자 분석 엔진"""
import json
from dataclasses import dataclass
from typing import Optional, List

from openai import OpenAI

from src.utils.config import OPENAI_API_KEY, OPENAI_MODEL
from src.utils.logger import get_logger
from src.utils.state import state

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
    """매수 분석"""
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

## 분석 요청
오늘 매수하기 좋은 종목을 최대 3개까지 추천해주세요.
확신도가 높을수록 비중을 높입니다.

각 종목에 대해 JSON 배열로 응답해주세요:
[
  {{
    "action": "buy",
    "stock_code": "종목코드",
    "stock_name": "종목명",
    "quantity": 0, // 0이면 자동 계산
    "price": 0, // 0이면 시장가
    "reason": "추천 이유",
    "confidence": 8 // 1-10
  }}
]

매수할 종목이 없으면 []을 반환하세요.
"""

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
            confidence = item.get("confidence", 5)
            price = item.get("price", 0)
            
            buy_amount = calculate_buy_amount(confidence, min_buy, max_buy, default_buy)
            
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
    if confidence >= 9:
        return max_amount
    elif confidence >= 7:
        return int(default_amount + (max_amount - default_amount) * (confidence - 6) / 4)
    elif confidence >= 5:
        return default_amount
    elif confidence >= 3:
        return int(min_amount + (default_amount - min_amount) * (confidence - 2) / 3)
    else:
        return min_amount


def analyze_for_sell(portfolio: list[dict], news_data: list) -> list[TradeDecision]:
    """매도 분석"""
    if not portfolio:
        return []
    
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 현재 보유 종목
{json.dumps(portfolio, ensure_ascii=False, indent=2)}

## 최신 뉴스
{json.dumps(news_data, ensure_ascii=False, indent=2)}

## 분석 요청
보유 종목 중 매도해야 할 종목을 선정해주세요. (손절/익절 포함)
매도할 종목만 JSON 배열로 응답해주세요.

[
  {{
    "action": "sell",
    "stock_code": "종목코드",
    "stock_name": "종목명",
    "quantity": 0, // 보유수량 전체 추천시
    "price": 0,
    "reason": "매도 이유",
    "confidence": 8
  }}
]
"""

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
                quantity=item.get("quantity", 0), # 실제 실행 시 보유량 체크 필요
                price=item.get("price", 0),
                reason=item.get("reason", ""),
                confidence=item.get("confidence", 5),
            ))
        
        return decisions
        
    except Exception as e:
        logger.error(f"매도 분석 실패: {e}")
        return []


def analyze_stock(stock_code: str, stock_name: str, current_price: float,
                  news: list = None) -> str:
    """개별 종목 분석"""
    prompt = f"""당신은 전문 주식 투자 분석가입니다.

## 분석 대상
- 종목: {stock_name} ({stock_code})
- 현재가: {current_price:,.2f}

## 뉴스
{json.dumps(news or [], ensure_ascii=False, indent=2)}

## 요청
이 종목의 투자 매력도, 단기 전망, 매수/매도 의견을 3-4문장으로 요약해주세요.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"분석 오류: {e}"


@dataclass
class StockRecommendation:
    """추천 종목 정보"""
    stock_code: str
    stock_name: str
    current_price: float
    change: float
    change_rate: float
    reason: str
    confidence: int


def get_daily_recommendations(market_data: dict, news_data: list, market: str = "KR") -> List[StockRecommendation]:
    """
    LLM 기반 추천 종목 조회
    market: "KR" or "US"
    """
    from src.trading import get_kis_client
    
    prompt = f"""당신은 전문 주식 투자 분석가입니다.
시장: {market} (한국 주식은 6자리 코드, 미국 주식은 티커)

## 뉴스 데이터
{json.dumps(news_data[:15], ensure_ascii=False, indent=2)}

## 요청
오늘 {market} 시장에서 매수하기 좋은 종목 3개를 추천해주세요.
단기 상승 가능성이 높은 종목 위주로 선정하세요.

JSON 배열로 응답:
[
  {{
    "stock_code": "005930" 또는 "AAPL",
    "stock_name": "종목명",
    "reason": "추천 이유",
    "confidence": 8
  }}
]
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict):
            result = result.get("recommendations", result.get("stocks", []))
        
        # 현재가 조회
        # 주의: get_daily_recommendations가 호출될 때,
        # KISClient가 해당 마켓 데이터를 조회할 수 있어야 함.
        # KR은 현재 설정된 계좌 상관없이 조회 가능하나, US는 해외시세 신청 계좌 필요할 수 있음.
        # 여기서는 state.get_mode()를 사용하되, US 추천의 경우 client 메서드 호출 주의.

        client = get_kis_client() # 현재 모드 클라이언트
        recommendations = []
        
        for item in result[:3]:
            code = str(item.get("stock_code", "")).strip()
            name = item.get("stock_name", "")
            
            try:
                current_price = 0
                change = 0
                rate = 0.0
                
                if market == "KR":
                    if len(code) == 6 and code.isdigit():
                        res = client.get_price(code)
                        output = res.get("output", {})
                        current_price = float(output.get("stck_prpr", 0))
                        change = float(output.get("prdy_vrss", 0))
                        rate = float(output.get("prdy_ctrt", 0))
                else:
                    # US
                    # 거래소 코드 추정 (임시: NAS)
                    res = client.get_overseas_price("NAS", code)
                    output = res.get("output", {})
                    current_price = float(output.get("last", 0))
                    # 해외주식 등락 정보는 API 응답 필드 확인 필요
                    # 여기서는 0으로 처리
                
                recommendations.append(StockRecommendation(
                    stock_code=code,
                    stock_name=name,
                    current_price=current_price,
                    change=change,
                    change_rate=rate,
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 5),
                ))
            except Exception as e:
                logger.warning(f"시세 조회 실패 ({code}): {e}")
                # 시세 조회 실패해도 추천 목록에는 넣되 가격 0 처리
                recommendations.append(StockRecommendation(
                    stock_code=code,
                    stock_name=name,
                    current_price=0,
                    change=0,
                    change_rate=0,
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 5),
                ))
        
        return recommendations
        
    except Exception as e:
        logger.error(f"추천 분석 실패: {e}")
        return []


def chat_with_llm(query: str, history: list = None) -> str:
    """
    일반적인 LLM 대화 (Discord 채팅용)

    Args:
        query: 사용자 질문
        history: 대화 기록 (선택 사항)

    Returns:
        LLM 응답
    """
    system_prompt = """당신은 주식 투자 및 경제 분야에 정통한 친절한 AI 어시스턴트입니다.
사용자의 질문에 대해 명확하고 도움이 되는 답변을 제공해주세요.
투자에 관련된 질문에는 신중하게 답변하고, 투자는 본인의 책임임을 상기시켜주는 것이 좋습니다."""

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": query})

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"LLM 채팅 실패: {e}")
        return f"죄송합니다. 답변을 생성하는 중에 문제가 발생했습니다: {e}"
