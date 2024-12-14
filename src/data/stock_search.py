"""종목 검색 모듈 - 종목명/티커로 검색"""
from typing import Optional, Tuple
import httpx

from src.utils.config import (
    KIS_API_KEY, 
    KIS_API_SECRET, 
    KIS_BASE_URL,
    TRADING_MODE,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 인기 종목 매핑 (종목명 -> 코드)
POPULAR_STOCKS = {
    # 한국 주식 (국내)
    "삼성전자": {"code": "005930", "market": "KR"},
    "SK하이닉스": {"code": "000660", "market": "KR"},
    "현대차": {"code": "005380", "market": "KR"},
    "기아": {"code": "000270", "market": "KR"},
    "네이버": {"code": "035420", "market": "KR"},
    "카카오": {"code": "035720", "market": "KR"},
    "LG에너지솔루션": {"code": "373220", "market": "KR"},
    "삼성바이오로직스": {"code": "207940", "market": "KR"},
    "삼성SDI": {"code": "006400", "market": "KR"},
    "POSCO홀딩스": {"code": "005490", "market": "KR"},
    "현대모비스": {"code": "012330", "market": "KR"},
    "LG화학": {"code": "051910", "market": "KR"},
    "신한지주": {"code": "055550", "market": "KR"},
    "KB금융": {"code": "105560", "market": "KR"},
    
    # 미국 주식 (해외)
    "애플": {"code": "AAPL", "market": "US", "exchange": "NAS"},
    "테슬라": {"code": "TSLA", "market": "US", "exchange": "NAS"},
    "엔비디아": {"code": "NVDA", "market": "US", "exchange": "NAS"},
    "마이크로소프트": {"code": "MSFT", "market": "US", "exchange": "NAS"},
    "구글": {"code": "GOOGL", "market": "US", "exchange": "NAS"},
    "아마존": {"code": "AMZN", "market": "US", "exchange": "NAS"},
    "메타": {"code": "META", "market": "US", "exchange": "NAS"},
    
    # 영문 티커 -> 한글 지원
    "AAPL": {"code": "AAPL", "market": "US", "exchange": "NAS", "name": "애플"},
    "TSLA": {"code": "TSLA", "market": "US", "exchange": "NAS", "name": "테슬라"},
    "NVDA": {"code": "NVDA", "market": "US", "exchange": "NAS", "name": "엔비디아"},
    "MSFT": {"code": "MSFT", "market": "US", "exchange": "NAS", "name": "마이크로소프트"},
    "GOOGL": {"code": "GOOGL", "market": "US", "exchange": "NAS", "name": "구글"},
    "AMZN": {"code": "AMZN", "market": "US", "exchange": "NAS", "name": "아마존"},
    "META": {"code": "META", "market": "US", "exchange": "NAS", "name": "메타"},
    "AMD": {"code": "AMD", "market": "US", "exchange": "NAS", "name": "AMD"},
    "INTC": {"code": "INTC", "market": "US", "exchange": "NAS", "name": "인텔"},
    "NFLX": {"code": "NFLX", "market": "US", "exchange": "NAS", "name": "넷플릭스"},
}


def search_stock(query: str) -> Optional[dict]:
    """
    종목명 또는 티커로 종목 검색
    
    Args:
        query: 종목명 또는 티커 (예: "삼성전자", "AAPL", "005930")
    
    Returns:
        종목 정보 딕셔너리 또는 None
    """
    query_upper = query.upper().strip()
    query_lower = query.lower().strip()
    
    # 1. 정확히 일치하는 종목명/티커 검색
    if query in POPULAR_STOCKS:
        return POPULAR_STOCKS[query]
    if query_upper in POPULAR_STOCKS:
        return POPULAR_STOCKS[query_upper]
    
    # 2. 한국 종목코드 (6자리 숫자)
    if query.isdigit() and len(query) == 6:
        return {"code": query, "market": "KR", "name": query}
    
    # 3. 미국 티커 (영문 대문자 1-5자리)
    if query_upper.isalpha() and 1 <= len(query_upper) <= 5:
        return {
            "code": query_upper, 
            "market": "US", 
            "exchange": "NAS",  # 기본값 나스닥
            "name": query_upper
        }
    
    # 4. 부분 일치 검색
    for name, info in POPULAR_STOCKS.items():
        if query in name or query_upper in name:
            return info
    
    return None


def get_stock_info(query: str) -> Tuple[str, str, str]:
    """
    종목 검색 및 정보 반환
    
    Args:
        query: 종목명 또는 티커
    
    Returns:
        (종목코드, 종목명, 시장구분) 튜플
        시장구분: "KR" (한국) 또는 "US" (미국)
    """
    result = search_stock(query)
    
    if result:
        code = result["code"]
        market = result["market"]
        name = result.get("name", query)
        exchange = result.get("exchange", "")
        
        return code, name, market, exchange
    
    return None, None, None, None
