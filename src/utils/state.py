"""전역 상태 관리"""

class GlobalState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.trading_mode = "paper"  # 기본값
        return cls._instance

    def set_mode(self, mode: str):
        if mode in ["real", "paper"]:
            self.trading_mode = mode

    def get_mode(self) -> str:
        return self.trading_mode

state = GlobalState()
