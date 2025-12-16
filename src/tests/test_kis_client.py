import pytest
from unittest.mock import MagicMock
from src.trading.kis_client import get_kis_client, KISClient

class TestKISClient:
    def test_init_paper_mode(self, mock_kis_config):
        """초기화 시 설정값 로드 확인 (모의투자)"""
        client = KISClient("paper")
        assert client.base_url == "https://paper.api.com"
        assert client.account_number == "22222222"

    def test_init_real_mode(self, mock_kis_config):
        """초기화 시 설정값 로드 확인 (실전투자)"""
        client = KISClient("real")
        assert client.base_url == "https://real.api.com"
        assert client.account_number == "11111111"

    def test_get_token_request(self, mock_http_client, mock_token_file):
        """토큰 발급 요청 테스트"""
        client = KISClient("paper")
        token = client._get_token()

        # httpx 호출 확인
        mock_http_client.post.assert_called()
        call_args = mock_http_client.post.call_args
        assert "/oauth2/tokenP" in call_args[0][0]
        assert token == "dummy_token"

    def test_get_balance_paper(self, mock_http_client, mock_token_file):
        """잔고 조회 테스트 (모의)"""
        client = KISClient("paper")
        # 토큰 미리 설정해서 _get_token 호출 방지 (선택사항)

        client.get_balance()

        mock_http_client.get.assert_called()
        call_args = mock_http_client.get.call_args
        url = call_args[0][0]
        headers = call_args[1]["headers"]

        assert "/uapi/domestic-stock/v1/trading/inquire-balance" in url
        # 모의투자는 TR_ID가 V로 시작해야 함 (TTTC8434R -> VTTC8434R)
        assert headers["tr_id"].startswith("V")

    def test_buy_stock_paper(self, mock_http_client, mock_token_file):
        """매수 주문 테스트 (모의)"""
        client = KISClient("paper")
        client.buy_stock("005930", 10, 0) # 삼성전자 10주 시장가

        mock_http_client.post.assert_called()
        call_args = mock_http_client.post.call_args
        headers = call_args[1]["headers"]
        body = call_args[1]["json"]

        assert headers["tr_id"].startswith("V")
        assert body["PDNO"] == "005930"
        assert body["ORD_QTY"] == "10"
        assert body["ORD_DVSN"] == "01" # 시장가

    def test_sell_stock_real(self, mock_http_client, mock_token_file):
        """매도 주문 테스트 (실전 - TR_ID 변경 없음 확인)"""
        client = KISClient("real")
        client.sell_stock("005930", 5, 70000) # 지정가

        mock_http_client.post.assert_called()
        call_args = mock_http_client.post.call_args
        headers = call_args[1]["headers"]
        body = call_args[1]["json"]

        # 실전은 T로 시작 (원래 TR_ID)
        assert headers["tr_id"].startswith("T")
        assert body["ORD_UNPR"] == "70000"
        assert body["ORD_DVSN"] == "00" # 지정가

    def test_api_error_handling(self, mock_http_client, mock_token_file):
        """API 에러 응답 처리 테스트"""
        # 에러 응답 설정
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"rt_cd": "1", "msg1": "Invalid Account"}
        mock_http_client.get.return_value = mock_response

        client = KISClient("paper")

        with pytest.raises(Exception) as excinfo:
            client.get_balance()

        assert "Invalid Account" in str(excinfo.value)
