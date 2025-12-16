import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime, timedelta
import httpx

from src.utils.state import state
from src.utils.config import KIS_CONFIG
from src.trading.momentum import scalping_positions

@pytest.fixture(autouse=True)
def reset_state():
    """모든 테스트 전에 GlobalState를 초기화"""
    state.set_mode("paper")
    yield
    state.set_mode("paper")

@pytest.fixture
def mock_kis_config(monkeypatch):
    """KIS_CONFIG를 더미 데이터로 패치"""
    dummy_config = {
        "real": {
            "base_url": "https://real.api.com",
            "app_key": "real_key",
            "app_secret": "real_secret",
            "account_number": "11111111",
            "account_product": "01",
        },
        "paper": {
            "base_url": "https://paper.api.com",
            "app_key": "paper_key",
            "app_secret": "paper_secret",
            "account_number": "22222222",
            "account_product": "01",
        }
    }
    monkeypatch.setattr("src.trading.kis_client.KIS_CONFIG", dummy_config)
    monkeypatch.setattr("src.utils.config.KIS_CONFIG", dummy_config)
    return dummy_config

@pytest.fixture
def mock_http_client(monkeypatch):
    """httpx.Client를 모의 객체로 대체"""
    mock_client_instance = MagicMock()

    # Context manager protocol (__enter__, __exit__)
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.__exit__.return_value = None

    # Response Mock
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"rt_cd": "0", "msg1": "SUCCESS", "access_token": "dummy_token", "token_type": "Bearer", "access_token_token_expired": (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")}

    # Methods
    mock_client_instance.post.return_value = mock_response
    mock_client_instance.get.return_value = mock_response

    # Patch httpx.Client to return our mock
    monkeypatch.setattr("httpx.Client", lambda *args, **kwargs: mock_client_instance)

    return mock_client_instance

@pytest.fixture
def mock_token_file(tmp_path, monkeypatch):
    """토큰 파일을 임시 경로로 변경하여 실제 파일 시스템 영향 방지"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("src.trading.kis_client.DATA_DIR", data_dir)
    return data_dir

@pytest.fixture
def mock_kis_client_for_momentum(monkeypatch):
    """momentum.py에서 사용하는 get_kis_client를 모킹"""
    mock_client = MagicMock()

    # 기본 성공 응답
    mock_client.buy_stock.return_value = {"rt_cd": "0", "msg1": "OK"}
    mock_client.sell_stock.return_value = {"rt_cd": "0", "msg1": "OK"}

    # 급등주 데이터 더미
    mock_client.get_rank_rising.return_value = {
        "output": [
            {
                "stck_shrn_iscd": "123456",
                "hts_kor_isnm": "TestStock",
                "prdy_ctrt": "10.0", # 10% 상승
                "acml_vol": "200000", # 20만주
                "stck_prpr": "10000" # 현재가 1만원
            },
            {
                "stck_shrn_iscd": "999999",
                "hts_kor_isnm": "BadStock",
                "prdy_ctrt": "2.0", # 등락률 낮음 (무시되어야 함)
                "acml_vol": "50000",
                "stck_prpr": "5000"
            }
        ]
    }

    monkeypatch.setattr("src.trading.momentum.get_kis_client", lambda mode: mock_client)
    return mock_client

@pytest.fixture
def clean_scalping_positions():
    scalping_positions.clear()
    yield
    scalping_positions.clear()
