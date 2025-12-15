"""종목 검색 모듈 - 종목명/티커로 검색"""
from typing import Optional, Tuple
import httpx

# KIS_CONFIG is imported but not used in search logic,
# but we keep it if future extensions need it.
# The previous regression was removing API_KEY constants but not updating usage if any existed.
# Here, search_stock doesn't use API keys, it uses static maps or pykrx.
# So removing the unused imports is safe.
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
    # 추가 종목
    "SK텔레콤": {"code": "017670", "market": "KR"},
    "KT": {"code": "030200", "market": "KR"},
    "하나금융지주": {"code": "086790", "market": "KR"},
    "SK이노베이션": {"code": "096770", "market": "KR"},
    "S-Oil": {"code": "010950", "market": "KR"},
    "HD한국조선해양": {"code": "009540", "market": "KR"},
    "한화오션": {"code": "042660", "market": "KR"},
    "신세계": {"code": "004170", "market": "KR"},
    "현대건설": {"code": "000720", "market": "KR"},
    "셀트리온": {"code": "068270", "market": "KR"},
    "크래프톤": {"code": "259960", "market": "KR"},
    "두산에너빌리티": {"code": "034020", "market": "KR"},
    
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


def _contains_korean(text: str) -> bool:
    """한글 포함 여부 확인"""
    return any('\uac00' <= char <= '\ud7a3' for char in text)


# 코스피/코스닥 종목 캐시 (종목명 -> 종목코드)
_KOSPI_CACHE: dict = {}
_CACHE_LOADED = False


def _load_kospi_cache():
    """pykrx로 코스피+코스닥 종목 캐시 로드"""
    global _KOSPI_CACHE, _CACHE_LOADED
    
    if _CACHE_LOADED:
        return
    
    try:
        from pykrx import stock as pykrx_stock
        from datetime import datetime
        
        today = datetime.now().strftime("%Y%m%d")
        
        # 코스피 + 코스닥 종목 로드
        for market in ["KOSPI", "KOSDAQ"]:
            tickers = pykrx_stock.get_market_ticker_list(today, market=market)
            for ticker in tickers:
                try:
                    name = pykrx_stock.get_market_ticker_name(ticker)
                    if name and isinstance(name, str):
                        _KOSPI_CACHE[name] = ticker
                except:
                    pass
        
        if _KOSPI_CACHE:
            logger.info(f"종목 캐시 로드 완료: {len(_KOSPI_CACHE)}개")
            _CACHE_LOADED = True
        else:
            logger.warning("pykrx 캐시 비어있음")
            
    except Exception as e:
        logger.warning(f"종목 캐시 로드 실패: {e}")


def _search_by_pykrx(query: str) -> Optional[dict]:
    """pykrx로 종목명 검색"""
    # 캐시 로드 시도
    _load_kospi_cache()
    
    # 정확히 일치
    if query in _KOSPI_CACHE:
        code = _KOSPI_CACHE[query]
        return {"code": code, "market": "KR", "name": query}
    
    # 부분 일치
    for name, code in _KOSPI_CACHE.items():
        if query in name:
            return {"code": code, "market": "KR", "name": name}
    
    # 실시간 조회 시도 (캐시에 없는 경우)
    try:
        from pykrx import stock as pykrx_stock
        
        # 코스피에서 검색
        for market in ["KOSPI", "KOSDAQ"]:
            tickers = pykrx_stock.get_market_ticker_list(market=market)
            for ticker in tickers:
                try:
                    name = pykrx_stock.get_market_ticker_name(ticker)
                    if name and query in name:
                        _KOSPI_CACHE[name] = ticker  # 캐시에 추가
                        return {"code": ticker, "market": "KR", "name": name}
                except:
                    pass
    except:
        pass
    
    return None


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
    
    # 1. 정확히 일치하는 종목명/티커 검색 (인기 종목)
    if query in POPULAR_STOCKS:
        result = POPULAR_STOCKS[query].copy()
        if "name" not in result:
            result["name"] = query
        return result
    if query_upper in POPULAR_STOCKS:
        result = POPULAR_STOCKS[query_upper].copy()
        if "name" not in result:
            result["name"] = query_upper
        return result
    
    # 2. 한국 종목코드 (6자리 숫자)
    if query.isdigit() and len(query) == 6:
        return {"code": query, "market": "KR", "name": query}
    
    # 3. 부분 일치 검색 (인기 종목)
    for name, info in POPULAR_STOCKS.items():
        if query in name or query_upper in name:
            result = info.copy()
            if "name" not in result:
                result["name"] = name
            return result
    
    # 4. pykrx로 동적 검색 (한글 종목명)
    if _contains_korean(query):
        result = _search_by_pykrx(query)
        if result:
            return result
        logger.warning(f"미등록 한국 종목: {query}")
        return None
    
    # 5. 미국 티커 (영문 대문자 1-5자리)
    if query_upper.isalpha() and 1 <= len(query_upper) <= 5:
        return {
            "code": query_upper, 
            "market": "US", 
            "exchange": "NAS",  # 기본값 나스닥
            "name": query_upper
        }
    
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
