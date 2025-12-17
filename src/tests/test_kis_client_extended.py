import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from src.trading.kis_client import KISClient, KISToken

class TestKISClientExtended:

    def test_load_token_success(self, mock_kis_config, mock_token_file):
        """기존 토큰 파일 로드 성공 테스트"""
        # 유효한 토큰 파일 생성
        token_data = {
            "access_token": "saved_token",
            "token_type": "Bearer",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat()
        }
        token_path = mock_token_file / "kis_token_paper.json"
        with open(token_path, "w") as f:
            json.dump(token_data, f)

        client = KISClient("paper")
        assert client.token is not None
        assert client.token.access_token == "saved_token"

    def test_load_token_expired(self, mock_kis_config, mock_token_file):
        """만료된 토큰 파일 로드 무시 테스트"""
        token_data = {
            "access_token": "expired_token",
            "token_type": "Bearer",
            "expires_at": (datetime.now() - timedelta(hours=1)).isoformat()
        }
        token_path = mock_token_file / "kis_token_paper.json"
        with open(token_path, "w") as f:
            json.dump(token_data, f)

        client = KISClient("paper")
        # 만료되었으므로 로드되지 않아야 함 (혹은 로드 후 _get_token에서 갱신됨을 확인)
        # 생성자에서는 일단 로드 시도하지만 유효성 검사 로직에 따라 다름.
        # 코드상 _load_token에서 expires_at > datetime.now() 체크함.
        assert client.token is None

    def test_save_token(self, mock_kis_config, mock_token_file):
        """토큰 저장 테스트"""
        client = KISClient("paper")
        client.token = KISToken(
            access_token="new_token",
            token_type="Bearer",
            expires_at=datetime.now() + timedelta(hours=2)
        )
        client._save_token()

        token_path = mock_token_file / "kis_token_paper.json"
        assert token_path.exists()
        with open(token_path, "r") as f:
            data = json.load(f)
            assert data["access_token"] == "new_token"

    def test_get_overseas_price(self, mock_http_client, mock_token_file):
        """해외 주식 현재가 조회 테스트"""
        client = KISClient("paper")
        client.get_overseas_price("NAS", "AAPL")

        mock_http_client.get.assert_called()
        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]

        assert params["EXCD"] == "NAS"
        assert params["SYMB"] == "AAPL"

    def test_get_overseas_balance(self, mock_http_client, mock_token_file):
        """해외 주식 잔고 조회 테스트"""
        client = KISClient("paper")
        client.get_overseas_balance()

        mock_http_client.get.assert_called()
        call_args = mock_http_client.get.call_args
        headers = call_args[1]["headers"]

        # 모의투자는 V로 시작
        assert headers["tr_id"].startswith("V")
        assert "VTTS3012R" in headers["tr_id"] # 코드상 확인된 ID

    def test_buy_overseas_stock(self, mock_http_client, mock_token_file):
        """해외 주식 매수 테스트"""
        client = KISClient("paper")
        client.buy_overseas_stock("NAS", "TSLA", 5, 200.0)

        mock_http_client.post.assert_called()
        call_args = mock_http_client.post.call_args
        headers = call_args[1]["headers"]
        body = call_args[1]["json"]

        assert headers["tr_id"] == "VTTS1002U" # 모의 매수
        assert body["OVRS_EXCG_CD"] == "NAS"
        assert body["PDNO"] == "TSLA"
        assert body["ORD_QTY"] == "5"

    def test_sell_overseas_stock(self, mock_http_client, mock_token_file):
        """해외 주식 매도 테스트"""
        client = KISClient("paper")
        client.sell_overseas_stock("NYS", "KO", 10, 60.0)

        mock_http_client.post.assert_called()
        call_args = mock_http_client.post.call_args
        headers = call_args[1]["headers"]

        assert headers["tr_id"] == "VTTS1001U" # 모의 매도

    def test_get_rank_rising(self, mock_http_client, mock_token_file):
        """급등주 조회 테스트"""
        client = KISClient("real") # 랭킹은 보통 실전 서버 데이터 사용하지만 함수 호출 테스트
        client.get_rank_rising()

        mock_http_client.get.assert_called()
        call_args = mock_http_client.get.call_args
        url = call_args[0][0]
        assert "ranking/fluctuation" in url
