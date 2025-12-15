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

# 한국투자증권 API 설정 (Real / Paper)
KIS_CONFIG = {
    "real": {
        "app_key": os.getenv("real_account_api_key"),
        "app_secret": os.getenv("real_account_api_secret"),
        "base_url": "https://openapi.koreainvestment.com:9443",
        "account_number": os.getenv("real_account_number"),
        "account_product": os.getenv("real_account_product", "01"),
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
