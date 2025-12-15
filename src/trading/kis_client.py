"""한국투자증권 API 클라이언트"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

import httpx

from src.utils.config import KIS_CONFIG
from src.utils.logger import get_logger
from src.utils.state import state

logger = get_logger(__name__)

# 토큰 저장 경로 (모드별 분리)
DATA_DIR = Path(__file__).parent.parent.parent / "data"


@dataclass
class KISToken:
    """토큰 정보"""
    access_token: str
    token_type: str
    expires_at: datetime


class KISClient:
    """한국투자증권 API 클라이언트"""
    
    def __init__(self, mode: str = "paper"):
        self.mode = mode
        config = KIS_CONFIG[mode]

        self.base_url = config["base_url"]
        self.app_key = config["app_key"]
        self.app_secret = config["app_secret"]
        self.account_number = config["account_number"]
        self.account_product = config["account_product"]

        self.token: Optional[KISToken] = None
        self.token_file = DATA_DIR / f"kis_token_{mode}.json"

        if not self.app_key or not self.app_secret:
            logger.warning(f"⚠️ {mode} 모드 API 키가 설정되지 않았습니다.")

        self._load_token()
    
    def _load_token(self):
        """저장된 토큰 로드"""
        if self.token_file.exists():
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if expires_at > datetime.now():
                        self.token = KISToken(
                            access_token=data["access_token"],
                            token_type=data["token_type"],
                            expires_at=expires_at,
                        )
                        logger.info(f"[{self.mode}] 기존 토큰 로드 완료")
            except Exception as e:
                logger.warning(f"[{self.mode}] 토큰 로드 실패: {e}")
    
    def _save_token(self):
        """토큰 저장"""
        if self.token:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w") as f:
                json.dump({
                    "access_token": self.token.access_token,
                    "token_type": self.token.token_type,
                    "expires_at": self.token.expires_at.isoformat(),
                }, f)
            logger.info(f"[{self.mode}] 토큰 저장 완료")
    
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
        logger.info(f"[{self.mode}] 새 토큰 발급 완료 (만료: {expires_at})")
        
        return self.token.access_token
    
    def _get_headers(self, tr_id: str) -> dict:
        """API 호출용 헤더 생성"""
        # 모의투자 TR_ID 변환
        real_tr_id = tr_id
        if self.mode == "paper" and tr_id[0] in ("T", "J", "C"):
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
        
        try:
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
                logger.error(f"[{self.mode}] API 에러: {error_msg}")
                raise Exception(f"KIS API Error ({self.mode}): {error_msg}")

            return data
        except Exception as e:
            logger.error(f"[{self.mode}] 요청 실패: {e}")
            raise

    # ==================== 조회 API ====================
    
    def get_balance(self) -> dict:
        """주식 잔고 조회"""
        tr_id = "TTTC8434R"
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        
        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
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
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        
        return self._request("GET", path, tr_id, params=params)
    
    def get_overseas_price(self, exchange: str, symbol: str) -> dict:
        """해외주식 현재가 조회"""
        tr_id = "HHDFS00000300"
        path = "/uapi/overseas-price/v1/quotations/price"
        
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol,
        }
        
        return self._request("GET", path, tr_id, params=params)

    def get_overseas_balance(self) -> dict:
        """해외주식 잔고 조회"""
        tr_id = "TTTS3012R"  # 해외주식 체결기준잔고
        path = "/uapi/overseas-stock/v1/trading/inquire-balance"

        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
            "OVRS_EXCG_CD": "NASD",  # NAS -> NASD (나스닥)
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        # 모의투자 TR ID 변경: VTTS3012R
        if self.mode == "paper":
            tr_id = "VTTS3012R"

        return self._request("GET", path, tr_id, params=params)

    # ==================== 주문 API (국내) ====================
    
    def buy_stock(self, stock_code: str, quantity: int, price: int = 0) -> dict:
        """국내 주식 매수 주문"""
        tr_id = "TTTC0802U"
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        ord_dvsn = "01" if price == 0 else "00"
        
        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        
        price_str = "시장가" if price == 0 else f"{price:,}원"
        logger.info(f"[{self.mode}] 국내 매수 주문: {stock_code} {quantity}주 @ {price_str}")
        return self._request("POST", path, tr_id, body=body)
    
    def sell_stock(self, stock_code: str, quantity: int, price: int = 0) -> dict:
        """국내 주식 매도 주문"""
        tr_id = "TTTC0801U"
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        
        ord_dvsn = "01" if price == 0 else "00"
        
        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }
        
        price_str = "시장가" if price == 0 else f"{price:,}원"
        logger.info(f"[{self.mode}] 국내 매도 주문: {stock_code} {quantity}주 @ {price_str}")
        return self._request("POST", path, tr_id, body=body)

    # ==================== 주문 API (해외) ====================

    def buy_overseas_stock(self, exchange: str, symbol: str, quantity: int, price: float = 0) -> dict:
        """해외 주식 매수 주문"""
        # 실전: TTTS1002U, 모의: VTTS1002U
        tr_id = "TTTS1002U"
        path = "/uapi/overseas-stock/v1/trading/order"

        if self.mode == "paper":
            tr_id = "VTTS1002U"

        # 해외주식 주문유형: 00(지정가), LOO(장개시지정가), LOC(장마감지정가) 등
        # 시장가 주문은 미국주식의 경우 지원이 제한적일 수 있으나 보통 지정가로 주문.
        # 가격 0이면 현재가 조회 후 지정가 주문이 안전하나, API상 0으로 보낼 수 있는지 확인 필요.
        # 여기서는 지정가 필수라고 가정하고, 0이면 에러 혹은 0으로 전송 시도.
        ord_dvsn = "00"

        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
            "OVRS_EXCG_CD": exchange, # NAS, NYS, AMS
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": ord_dvsn,
        }

        logger.info(f"[{self.mode}] 해외 매수 주문: {exchange} {symbol} {quantity}주 @ ${price}")
        return self._request("POST", path, tr_id, body=body)

    def sell_overseas_stock(self, exchange: str, symbol: str, quantity: int, price: float = 0) -> dict:
        """해외 주식 매도 주문"""
        # 실전: TTTS1001U, 모의: VTTS1001U
        tr_id = "TTTS1001U"
        path = "/uapi/overseas-stock/v1/trading/order"

        if self.mode == "paper":
            tr_id = "VTTS1001U"

        ord_dvsn = "00"

        body = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(price),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": ord_dvsn,
        }

        logger.info(f"[{self.mode}] 해외 매도 주문: {exchange} {symbol} {quantity}주 @ ${price}")
        return self._request("POST", path, tr_id, body=body)

    # ==================== 랭킹/분석 API (추가) ====================

    def get_rank_rising(self) -> dict:
        """급등주 조회 (전일대비 상승률 상위)"""
        tr_id = "FHPST01700000"
        path = "/uapi/domestic-stock/v1/ranking/fluctuation"

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": "0000",  # 전체
            "fid_rank_sort_cls_code": "0", # 상승순
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "0",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_tr_da_excd": "",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        }

        return self._request("GET", path, tr_id, params=params)


# 클라이언트 인스턴스 관리
_clients: Dict[str, KISClient] = {}

def get_kis_client(mode: str = None) -> KISClient:
    """
    KIS 클라이언트 반환 (싱글톤 패턴)
    mode: 'real' or 'paper'. None이면 state.get_mode() 사용
    """
    if mode is None:
        mode = state.get_mode()

    if mode not in _clients:
        _clients[mode] = KISClient(mode)

    return _clients[mode]
