"""
Multi-Account 기능 테스트

테스트 실행:
  cd /home/ubuntu/i-am-the-best-investor
  .venv/bin/python -m pytest src/tests/test_multi_account.py -v

실제 API 연동 테스트 (네트워크 필요):
  .venv/bin/python -m pytest src/tests/test_multi_account.py -v -m "not mock_only" --run-live
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ==================== Unit Tests (Mock, 네트워크 불필요) ====================

class TestRealAccountDiscovery:
    """config.py: 실전 계좌 자동 탐색 테스트"""

    def test_discover_real_accounts(self, monkeypatch):
        """realNN_* 환경변수에서 계좌 자동 탐색"""
        env = {
            "real01_account_api_key": "key01",
            "real01_account_api_secret": "secret01",
            "real01_account_number": "11111111",
            "real01_account_product": "01",
            "real02_account_api_key": "key02",
            "real02_account_api_secret": "secret02",
            "real02_account_number": "22222222",
            "real02_account_product": "01",
        }
        monkeypatch.setattr("os.getenv", lambda k, default=None: env.get(k, default))

        from src.utils.config import _discover_real_accounts
        accounts = _discover_real_accounts()

        assert len(accounts) == 2
        assert accounts[0]["id"] == "real01"
        assert accounts[0]["account_number"] == "11111111"
        assert accounts[1]["id"] == "real02"
        assert accounts[1]["account_number"] == "22222222"

    def test_discover_no_accounts(self, monkeypatch):
        """환경변수 없을 때 빈 리스트"""
        monkeypatch.setattr("os.getenv", lambda k, default=None: default)

        from src.utils.config import _discover_real_accounts
        accounts = _discover_real_accounts()

        assert accounts == []

    def test_get_real_account_by_number(self):
        """계좌번호로 조회"""
        from src.utils.config import get_real_account_by_number, REAL_ACCOUNTS
        if not REAL_ACCOUNTS:
            pytest.skip("No real accounts configured")

        first = REAL_ACCOUNTS[0]
        result = get_real_account_by_number(first["account_number"])
        assert result is not None
        assert result["account_number"] == first["account_number"]

    def test_get_real_account_by_number_not_found(self):
        """존재하지 않는 계좌번호"""
        from src.utils.config import get_real_account_by_number
        result = get_real_account_by_number("99999999")
        assert result is None

    def test_get_real_account_by_id(self):
        """ID(real01 등)로 조회"""
        from src.utils.config import get_real_account_by_id, REAL_ACCOUNTS
        if not REAL_ACCOUNTS:
            pytest.skip("No real accounts configured")

        result = get_real_account_by_id("real01")
        assert result is not None
        assert result["id"] == "real01"


class TestGlobalStateMultiAccount:
    """state.py: 계좌 선택 상태 관리 테스트"""

    def test_default_account_is_first(self):
        """기본 선택 계좌는 첫 번째 real 계좌"""
        from src.utils.state import state
        from src.utils.config import REAL_ACCOUNTS

        state._real_account_number = None  # reset
        if not REAL_ACCOUNTS:
            pytest.skip("No real accounts configured")

        assert state.get_real_account_number() == REAL_ACCOUNTS[0]["account_number"]

    def test_set_valid_account(self):
        """유효한 계좌번호 설정"""
        from src.utils.state import state
        from src.utils.config import REAL_ACCOUNTS

        if len(REAL_ACCOUNTS) < 2:
            pytest.skip("Need at least 2 real accounts")

        acc2 = REAL_ACCOUNTS[1]
        result = state.set_real_account(acc2["account_number"])
        assert result is True
        assert state.get_real_account_number() == acc2["account_number"]

        # cleanup
        state._real_account_number = None

    def test_set_invalid_account(self):
        """잘못된 계좌번호 설정 시 False 반환"""
        from src.utils.state import state

        result = state.set_real_account("00000000")
        assert result is False


class TestKISClientMultiAccount:
    """kis_client.py: 계좌별 클라이언트 인스턴스 테스트"""

    def test_different_accounts_different_clients(self, mock_kis_config, mock_token_file):
        """다른 계좌번호 → 다른 클라이언트 인스턴스"""
        from src.trading.kis_client import get_kis_client, _clients, KISClient
        from src.utils.config import REAL_ACCOUNTS
        _clients.clear()

        if len(REAL_ACCOUNTS) < 2:
            pytest.skip("Need at least 2 real accounts")

        acc1 = REAL_ACCOUNTS[0]["account_number"]
        acc2 = REAL_ACCOUNTS[1]["account_number"]

        client1 = get_kis_client("real", account_number=acc1)
        client2 = get_kis_client("real", account_number=acc2)

        assert client1 is not client2
        assert client1.account_number == acc1
        assert client2.account_number == acc2

        _clients.clear()

    def test_same_account_same_client(self, mock_kis_config, mock_token_file):
        """같은 계좌번호 → 같은 클라이언트 인스턴스 (싱글톤)"""
        from src.trading.kis_client import get_kis_client, _clients
        from src.utils.config import REAL_ACCOUNTS
        _clients.clear()

        if not REAL_ACCOUNTS:
            pytest.skip("No real accounts configured")

        acc = REAL_ACCOUNTS[0]["account_number"]
        client_a = get_kis_client("real", account_number=acc)
        client_b = get_kis_client("real", account_number=acc)

        assert client_a is client_b

        _clients.clear()

    def test_paper_mode_unchanged(self, mock_kis_config, mock_token_file):
        """paper 모드는 기존 동작 유지"""
        from src.trading.kis_client import get_kis_client, _clients
        _clients.clear()

        client = get_kis_client("paper")
        assert client.mode == "paper"

        client2 = get_kis_client("paper")
        assert client is client2

        _clients.clear()

    def test_account_specific_token_file(self, mock_kis_config, mock_token_file):
        """계좌별 토큰 파일 경로 분리"""
        from src.trading.kis_client import KISClient

        config = {
            "id": "real01",
            "app_key": "test_key",
            "app_secret": "test_secret",
            "base_url": "https://test.com",
            "account_number": "11111111",
            "account_product": "01",
        }
        client = KISClient("real", account_config=config)
        assert "real01" in str(client.token_file)


class TestKISConfigBackwardCompat:
    """KIS_CONFIG 하위 호환성 테스트"""

    def test_kis_config_has_real_and_paper(self):
        """KIS_CONFIG에 real, paper 키 존재"""
        from src.utils.config import KIS_CONFIG
        assert "real" in KIS_CONFIG
        assert "paper" in KIS_CONFIG

    def test_kis_config_real_has_required_fields(self):
        """KIS_CONFIG['real']에 필수 필드 존재"""
        from src.utils.config import KIS_CONFIG
        real = KIS_CONFIG["real"]
        for field in ["app_key", "app_secret", "base_url", "account_number", "account_product"]:
            assert field in real, f"Missing field: {field}"


# ==================== Live API Tests (네트워크 필요) ====================

def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False, help="Run live API tests")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live"):
        skip = pytest.mark.skip(reason="need --run-live option to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)


@pytest.mark.live
class TestLiveAPI:
    """실제 KIS API 연동 테스트 (--run-live 필요)"""

    def test_real02_portfolio(self):
        """real02 계좌 포트폴리오 조회"""
        from src.utils.state import state
        from src.utils.config import REAL_ACCOUNTS
        from src.trading.kis_client import get_kis_client, _clients
        _clients.clear()

        if len(REAL_ACCOUNTS) < 2:
            pytest.skip("real02 account not configured")

        acc = REAL_ACCOUNTS[1]
        state.set_mode("real")
        state.set_real_account(acc["account_number"])

        client = get_kis_client()
        assert client.account_number == acc["account_number"]

        balance = client.get_balance()
        assert balance.get("rt_cd") == "0"

        output2 = balance.get("output2", [{}])[0]
        total = int(output2.get("tot_evlu_amt", 0))
        cash = int(output2.get("dnca_tot_amt", 0))

        print(f"\n=== real02 (****{acc['account_number'][-4:]}) ===")
        print(f"총 평가금액: {total:,}원 | 예수금: {cash:,}원")

        holdings = balance.get("output1", [])
        for h in holdings:
            print(f"  {h.get('prdt_name')}: {h.get('hldg_qty')}주 ({float(h.get('evlu_pfls_rt', 0)):+.2f}%)")

        # cleanup
        state._real_account_number = None
        _clients.clear()

    def test_real01_portfolio(self):
        """real01 계좌 포트폴리오 조회"""
        from src.utils.state import state
        from src.utils.config import REAL_ACCOUNTS
        from src.trading.kis_client import get_kis_client, _clients
        _clients.clear()

        if not REAL_ACCOUNTS:
            pytest.skip("No real accounts configured")

        acc = REAL_ACCOUNTS[0]
        state.set_mode("real")
        state.set_real_account(acc["account_number"])

        client = get_kis_client()
        assert client.account_number == acc["account_number"]

        balance = client.get_balance()
        assert balance.get("rt_cd") == "0"

        output2 = balance.get("output2", [{}])[0]
        total = int(output2.get("tot_evlu_amt", 0))
        cash = int(output2.get("dnca_tot_amt", 0))

        print(f"\n=== real01 (****{acc['account_number'][-4:]}) ===")
        print(f"총 평가금액: {total:,}원 | 예수금: {cash:,}원")

        holdings = balance.get("output1", [])
        for h in holdings:
            print(f"  {h.get('prdt_name')}: {h.get('hldg_qty')}주 ({float(h.get('evlu_pfls_rt', 0)):+.2f}%)")

        # cleanup
        state._real_account_number = None
        _clients.clear()
