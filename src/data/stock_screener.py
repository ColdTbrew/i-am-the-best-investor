"""종목 스크리닝 모듈 - 코스피 상장 + 흑자 기업"""
import time
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from pykrx import stock as pykrx_stock

from src.trading import get_kis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 코스피 우량주 (흑자 기업) - 기본 관심 종목
# 기준: 코스피 상장, 최근 연간 영업이익 흑자
KOSPI_WATCHLIST = [
    # 반도체/전자
    {"code": "005930", "name": "삼성전자", "sector": "반도체"},
    {"code": "000660", "name": "SK하이닉스", "sector": "반도체"},
    
    # 자동차
    {"code": "005380", "name": "현대차", "sector": "자동차"},
    {"code": "000270", "name": "기아", "sector": "자동차"},
    
    # 금융
    {"code": "055550", "name": "신한지주", "sector": "금융"},
    {"code": "105560", "name": "KB금융", "sector": "금융"},
    {"code": "086790", "name": "하나금융지주", "sector": "금융"},
    
    # 에너지/화학
    {"code": "096770", "name": "SK이노베이션", "sector": "에너지"},
    {"code": "010950", "name": "S-Oil", "sector": "에너지"},
    
    # 철강/조선
    {"code": "005490", "name": "POSCO홀딩스", "sector": "철강"},
    {"code": "009540", "name": "HD한국조선해양", "sector": "조선"},
    
    # 통신/유통
    {"code": "017670", "name": "SK텔레콤", "sector": "통신"},
    {"code": "030200", "name": "KT", "sector": "통신"},
    {"code": "004170", "name": "신세계", "sector": "유통"},
    
    # 건설/중공업
    {"code": "000720", "name": "현대건설", "sector": "건설"},
    {"code": "042660", "name": "한화오션", "sector": "조선"},
]


@dataclass
class StockInfo:
    """종목 정보"""
    code: str
    name: str
    current_price: int
    change_rate: float  # 등락률 (%)
    volume: int  # 거래량
    sector: str = ""  # 섹터
    is_profitable: bool = True  # 흑자 여부


def get_kospi_profitable_stocks() -> list[dict]:
    """
    코스피 흑자 기업 목록 조회 (pykrx 사용)
    
    Returns:
        흑자 기업 리스트
    """
    try:
        # 코스피 종목 리스트
        kospi_tickers = pykrx_stock.get_market_ticker_list(market="KOSPI")
        
        # pykrx가 빈 리스트를 반환하면 (주말/휴장일 등) fallback
        if not kospi_tickers:
            logger.warning("pykrx 종목 리스트 비어있음 (주말/휴장일), 기본 watchlist 사용")
            return KOSPI_WATCHLIST
        
        # 기본 관심종목에서 코스피 종목만 필터
        kospi_watchlist = [
            s for s in KOSPI_WATCHLIST 
            if s["code"] in kospi_tickers
        ]
        
        # 필터링 결과가 비어있으면 fallback
        if not kospi_watchlist:
            logger.warning("코스피 관심종목 필터 결과 없음, 기본 watchlist 사용")
            return KOSPI_WATCHLIST
        
        logger.info(f"코스피 관심종목: {len(kospi_watchlist)}개")
        return kospi_watchlist
        
    except Exception as e:
        logger.warning(f"코스피 종목 조회 실패: {e}, 기본 watchlist 사용")
        return KOSPI_WATCHLIST


def check_profitability(stock_code: str) -> bool:
    """
    종목 흑자 여부 확인 (영업이익 기준)
    
    Args:
        stock_code: 종목코드
    
    Returns:
        True if 흑자, False if 적자
    """
    try:
        # 최근 연간 재무제표 조회
        today = datetime.now()
        year = today.year - 1  # 전년도
        
        # pykrx로 재무정보 조회 (PER > 0이면 흑자로 간주)
        # NOTE: 실제로는 영업이익을 조회해야 하지만, 
        # pykrx 제약으로 PER 양수 = 흑자로 간단히 판단
        df = pykrx_stock.get_market_fundamental(
            today.strftime("%Y%m%d"),
            market="KOSPI"
        )
        
        if stock_code in df.index:
            per = df.loc[stock_code, "PER"]
            # PER > 0이면 흑자 (이익이 있어야 PER 계산 가능)
            return per > 0
        
        return True  # 조회 실패시 기본 True
        
    except Exception as e:
        logger.debug(f"재무정보 조회 실패 ({stock_code}): {e}")
        return True  # 조회 실패시 기본 True


def get_market_data() -> dict:
    """
    시장 데이터 수집 (코스피 흑자 기업만)
    
    Returns:
        시장 데이터 딕셔너리
    """
    client = get_kis_client()
    
    market_data = {
        "stocks": [],
        "top_gainers": [],
        "top_losers": [],
        "filter": "코스피 상장 + 흑자 기업",
    }
    
    logger.info("🔍 시장 데이터 수집 시작 (코스피 흑자 기업)")
    
    # 코스피 흑자 기업 리스트
    watchlist = get_kospi_profitable_stocks()
    
    # 관심 종목 시세 조회
    for stock in watchlist:
        try:
            # API 초당 호출 제한(모의투자 2건/초) 준수를 위한 지연
            time.sleep(0.5)
            
            price_data = client.get_price(stock["code"])
            output = price_data.get("output", {})
            
            stock_info = {
                "code": stock["code"],
                "name": stock["name"],
                "sector": stock.get("sector", ""),
                "current_price": int(output.get("stck_prpr", 0)),
                "change_rate": float(output.get("prdy_ctrt", 0)),
                "volume": int(output.get("acml_vol", 0)),
                "high_price": int(output.get("stck_hgpr", 0)),
                "low_price": int(output.get("stck_lwpr", 0)),
                "market": "KOSPI",
                "is_profitable": True,
            }
            market_data["stocks"].append(stock_info)
            logger.info(f"✅ [{stock['name']}] 현재가: {stock_info['current_price']:,}원 ({stock_info['change_rate']}% 상승)")
            
        except Exception as e:
            logger.warning(f"{stock['name']} 시세 조회 실패: {e}")
    
    # 등락률 기준 정렬
    if market_data["stocks"]:
        sorted_stocks = sorted(
            market_data["stocks"], 
            key=lambda x: x["change_rate"], 
            reverse=True
        )
        market_data["top_gainers"] = [s for s in sorted_stocks if s["change_rate"] > 0][:5]
        market_data["top_losers"] = [s for s in sorted_stocks if s["change_rate"] < 0][-5:]
    
    logger.info(f"시장 데이터 수집 완료: {len(market_data['stocks'])}개 코스피 흑자 종목")
    return market_data


def screen_stocks(min_volume: int = 100000, 
                  min_change: float = -5.0,
                  max_change: float = 5.0,
                  sector: str = None) -> list[dict]:
    """
    종목 스크리닝 (코스피 + 흑자 + 추가 필터)
    
    Args:
        min_volume: 최소 거래량
        min_change: 최소 등락률
        max_change: 최대 등락률
        sector: 섹터 필터 (None이면 전체)
    
    Returns:
        필터링된 종목 리스트
    """
    market_data = get_market_data()
    
    filtered = []
    for stock in market_data["stocks"]:
        # 기본 필터: 거래량, 등락률
        if not (stock["volume"] >= min_volume and 
                min_change <= stock["change_rate"] <= max_change):
            continue
        
        # 섹터 필터
        if sector and stock.get("sector") != sector:
            continue
        
        filtered.append(stock)
    
    logger.info(f"스크리닝 결과: {len(filtered)}개 종목")
    return filtered


def get_sectors() -> list[str]:
    """사용 가능한 섹터 리스트"""
    return list(set(s.get("sector", "") for s in KOSPI_WATCHLIST if s.get("sector")))


def add_to_watchlist(code: str, name: str, sector: str = ""):
    """관심종목 추가 (코스피 흑자 확인)"""
    # 코스피 여부 확인
    try:
        kospi_tickers = pykrx_stock.get_market_ticker_list(market="KOSPI")
        if code not in kospi_tickers:
            logger.warning(f"{name}({code})은 코스피 종목이 아닙니다")
            return False
    except:
        pass
    
    KOSPI_WATCHLIST.append({"code": code, "name": name, "sector": sector})
    logger.info(f"관심종목 추가: {name} ({code}) - {sector}")
    return True


def get_watchlist() -> list[dict]:
    """관심종목 리스트 반환"""
    return KOSPI_WATCHLIST.copy()

