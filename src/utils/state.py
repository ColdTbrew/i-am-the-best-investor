"""전역 상태 관리"""

class GlobalState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.trading_mode = "real"  # 기본값
            cls._instance.discord_bot = None  # 디스코드 봇 인스턴스
            cls._instance._real_account_number = None  # real 계좌번호 (None이면 첫 번째 계좌)
        return cls._instance

    def set_mode(self, mode: str):
        if mode in ["real", "paper"]:
            self.trading_mode = mode

    def get_mode(self) -> str:
        return self.trading_mode

    def set_real_account(self, account_number: str):
        """사용할 real 계좌번호 설정"""
        from src.utils.config import get_real_account_by_number
        account = get_real_account_by_number(account_number)
        if account:
            self._real_account_number = account_number
            return True
        return False

    def get_real_account_number(self) -> str:
        """현재 선택된 real 계좌번호 반환"""
        if self._real_account_number:
            return self._real_account_number
        # 기본값: 첫 번째 real 계좌
        from src.utils.config import REAL_ACCOUNTS
        if REAL_ACCOUNTS:
            return REAL_ACCOUNTS[0]["account_number"]
        return None

state = GlobalState()

