"""LLM 기반 자동매매 봇 - 설정 관리"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 기본 거래 모드 (초기값)
DEFAULT_TRADING_MODE = os.getenv("TRADING_MODE", "paper")

# 한국투자증권 API 설정

# 동적 real 계좌 탐색 (real01_*, real02_*, ... real99_*)
def _discover_real_accounts():
    """환경변수에서 realNN_account_* 패턴으로 등록된 계좌들을 자동 탐색"""
    accounts = []
    for i in range(1, 100):
        prefix = f"real{i:02d}"
        api_key = os.getenv(f"{prefix}_account_api_key")
        if not api_key:
            continue
        accounts.append({
            "id": prefix,
            "app_key": api_key,
            "app_secret": os.getenv(f"{prefix}_account_api_secret"),
            "base_url": "https://openapi.koreainvestment.com:9443",
            "account_number": os.getenv(f"{prefix}_account_number"),
            "account_product": os.getenv(f"{prefix}_account_product", "01"),
        })
    return accounts

REAL_ACCOUNTS = _discover_real_accounts()

def get_real_account_by_number(account_number: str) -> dict:
    """계좌번호로 real 계좌 설정을 조회"""
    for acc in REAL_ACCOUNTS:
        if acc["account_number"] == account_number:
            return acc
    return None

def get_real_account_by_id(account_id: str) -> dict:
    """ID(real01, real02 등)로 real 계좌 설정을 조회"""
    for acc in REAL_ACCOUNTS:
        if acc["id"] == account_id:
            return acc
    return None

KIS_CONFIG = {
    # real 기본값: 첫 번째 발견된 계좌 (하위 호환)
    "real": REAL_ACCOUNTS[0] if REAL_ACCOUNTS else {
        "app_key": None,
        "app_secret": None,
        "base_url": "https://openapi.koreainvestment.com:9443",
        "account_number": None,
        "account_product": "01",
    },
    "paper": {
        "app_key": os.getenv("fake_account_api_key"),
        "app_secret": os.getenv("fake_account_api_secret"),
        "base_url": "https://openapivts.koreainvestment.com:29443",
        "account_number": os.getenv("fake_account_number"),
        "account_product": os.getenv("fake_account_product", "01"),
    }
}

# OpenAI API
OPENAI_API_KEY = os.getenv("openai_api_key")
OPENAI_MODEL = "gpt-5-nano"

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# 리스크 관리 설정
RISK_CONFIG = {
    # 매수 제한
    "max_buy_per_day": 3,              # 하루 최대 매수 종목 수
    "max_position_ratio": 0.2,          # 종목당 최대 비중 (20%)
    
    # 매수 금액 설정
    "min_buy_amount": 100000,           # 최소 매수 금액 (10만원)
    "max_buy_amount": 5000000,          # 최대 매수 금액 (500만원)
    "buy_amount_per_stock": 1000000,    # 종목당 기본 매수 금액 (100만원)
    
    # 손익 관리
    "stop_loss_rate": -0.05,            # 손절 라인 (-5%)
    "take_profit_rate": 0.15,           # 익절 라인 (+15%)
    "max_daily_loss": -0.03,            # 일일 최대 손실 (-3%)

    # 급등주 단타 설정
    "scalping_amount": 100000,          # 단타 진입 금액 (10만원)
}

# 스케줄 설정
SCHEDULE_CONFIG = {
    "market_open": "09:00",
    "market_close": "15:30",
    "bot_start": "11:59",
    "analysis_time": "08:45",
    "order_time": "09:00",
    "kr_morning_routine": "08:00",
    "us_evening_routine": "22:00",
}
