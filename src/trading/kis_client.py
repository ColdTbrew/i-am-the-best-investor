"""한국투자증권 API 클라이언트"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import httpx

from src.utils.config import (
    KIS_API_KEY,
    KIS_API_SECRET,
    KIS_BASE_URL,
    KIS_ACCOUNT_NUMBER,
    KIS_ACCOUNT_PRODUCT,
    TRADING_MODE,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 토큰 저장 경로
TOKEN_FILE = Path(__file__).parent.parent.parent / "data" / "kis_token.json"


@dataclass
class KISToken:
    """토큰 정보"""
    access_token: str
    token_type: str
    expires_at: datetime


class KISClient:
    """한국투자증권 API 클라이언트"""
    
    def __init__(self):
        self.base_url = KIS_BASE_URL
        self.app_key = KIS_API_KEY
        self.app_secret = KIS_API_SECRET
        self.account_number = KIS_ACCOUNT_NUMBER  # 계좌번호 8자리
        self.account_product = KIS_ACCOUNT_PRODUCT  # 상품코드 2자리
        self.token: Optional[KISToken] = None
        self._load_token()
    
    def _load_token(self):
        """저장된 토큰 로드"""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r") as f:
                    data = json.load(f)
                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if expires_at > datetime.now():
                        self.token = KISToken(
                            access_token=data["access_token"],
                            token_type=data["token_type"],
                            expires_at=expires_at,
                        )
                        logger.info("기존 토큰 로드 완료")
            except Exception as e:
                logger.warning(f"토큰 로드 실패: {e}")
    
    def _save_token(self):
        """토큰 저장"""
        if self.token:
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": self.token.access_token,
                    "token_type": self.token.token_type,
                    "expires_at": self.token.expires_at.isoformat(),
                }, f)
            logger.info("토큰 저장 완료")
    
    def _get_token(self) -> str:
        """유효한 토큰 반환, 필요시 발급"""
        if self.token and self.token.expires_at > datetime.now():
            return self.token.access_token
        
        # 토큰 발급
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        
        with httpx.Client() as client:
            res = client.post(url, headers=headers, json=body)
            res.raise_for_status()
            data = res.json()
        
        # 토큰 저장
        expires_at = datetime.strptime(
            data["access_token_token_expired"], 
            "%Y-%m-%d %H:%M:%S"
        )
        self.token = KISToken(
            access_token=data["access_token"],
            token_type=data["token_type"],
            expires_at=expires_at,
        )
        self._save_token()
        logger.info(f"새 토큰 발급 완료 (만료: {expires_at})")
        
        return self.token.access_token
    
    def _get_headers(self, tr_id: str) -> dict:
        """API 호출용 헤더 생성"""
        # 모의투자 TR_ID 변환
        if TRADING_MODE == "paper" and tr_id[0] in ("T", "J", "C"):
            tr_id = "V" + tr_id[1:]
        
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
    
    def _request(self, method: str, path: str, tr_id: str, 
                 params: dict = None, body: dict = None) -> dict:
        """API 요청 공통 함수"""
        url = f"{self.base_url}{path}"
        headers = self._get_headers(tr_id)
        
        with httpx.Client(timeout=30) as client:
            if method == "GET":
                res = client.get(url, headers=headers, params=params)
            else:
                res = client.post(url, headers=headers, json=body)
            
            res.raise_for_status()
            data = res.json()
        
        # 에러 체크
        if data.get("rt_cd") != "0":
            error_msg = data.get("msg1", "Unknown error")
            logger.error(f"API 에러: {error_msg}")
            raise Exception(f"KIS API Error: {error_msg}")
        
        return data
    
    # ==================== 조회 API ====================
    
    def get_balance(self) -> dict:
        """주식 잔고 조회"""
        # 실전: TTTC8434R, 모의: VTTC8434R
        tr_id = "TTTC8434R"
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        
        # 계좌번호
        params = {
            "CANO": self.account_number,  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": self.account_product,  # 계좌상품코드
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        
        return self._request("GET", path, tr_id, params=params)
    
    def get_price(self, stock_code: str) -> dict:
        """국내주식 현재가 조회"""
        tr_id = "FHKST01010100"
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식
            "FID_INPUT_ISCD": stock_code,
        }
        
        return self._request("GET", path, tr_id, params=params)
    
    def get_overseas_price(self, exchange: str, symbol: str) -> dict:
        """
        해외주식 현재가 조회
        
        Args:
            exchange: 거래소코드 (NAS:나스닥, NYS:뉴욕, AMS:아멕스, etc)
            symbol: 티커 (예: AAPL, TSLA)
        """
        tr_id = "HHDFS00000300"  # 해외주식 현재가
        path = "/uapi/overseas-price/v1/quotations/price"
        
        params = {
            "AUTH": "",
            "EXCD": exchange,  # 거래소코드
            "SYMB": symbol,    # 종목코드
        }
        
        return self._request("GET", path, tr_id, params=params)
    
    # ==================== 주문 API ====================
    
    def buy_stock(self, stock_code: str, quantity: int, price: int = 0) -> dict:
        """주식 매수 주문
        
        Args:
            stock_code: 종목코드 (6자리)
            quantity: 주문 수량
            price: 주문 가격 (0이면 시장가)
        """
        tr_id = "TTTC0802U"  # 매수
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        # 주문 유형: 00(지정가), 01(시장가)
        ord_dvsn = "01" if price == 0 else "00"
        
        body = {
            "CANO": self.account_number,  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": self.account_product,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        
        logger.info(f"매수 주문: {stock_code} {quantity}주 @ {price}원")
        return self._request("POST", path, tr_id, body=body)
    
    def sell_stock(self, stock_code: str, quantity: int, price: int = 0) -> dict:
        """주식 매도 주문
        
        Args:
            stock_code: 종목코드 (6자리)
            quantity: 주문 수량
            price: 주문 가격 (0이면 시장가)
        """
        tr_id = "TTTC0801U"  # 매도
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        ord_dvsn = "01" if price == 0 else "00"
        
        body = {
            "CANO": self.account_number,  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": self.account_product,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        
        logger.info(f"매도 주문: {stock_code} {quantity}주 @ {price}원")
        return self._request("POST", path, tr_id, body=body)


# 싱글톤 인스턴스
_client: Optional[KISClient] = None


def get_kis_client() -> KISClient:
    """KIS 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        _client = KISClient()
    return _client
