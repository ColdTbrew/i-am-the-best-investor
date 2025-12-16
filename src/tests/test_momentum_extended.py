import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
import src.trading.momentum as momentum_module
from src.trading.momentum import load_state, save_state, check_momentum_and_scalp

class TestMomentumExtended:

    def test_load_save_state(self, tmp_path, monkeypatch):
        """상태 저장 및 로드 테스트"""
        # 상태 파일 경로를 임시 경로로 변경
        state_file = tmp_path / "scalping_state.json"
        monkeypatch.setattr("src.trading.momentum.STATE_FILE", state_file)

        # 1. 저장 테스트
        now = datetime.now()
        test_pos = {
            "code": "123456",
            "name": "SaveTest",
            "qty": 10,
            "buy_price": 1000,
            "time": now
        }
        # 모듈 변수 직접 접근
        momentum_module.scalping_positions.append(test_pos)
        save_state()

        assert state_file.exists()

        # 2. 로드 테스트
        momentum_module.scalping_positions.clear()
        load_state()

        # load_state가 scalping_positions를 재할당하므로 모듈을 통해 확인해야 함
        assert len(momentum_module.scalping_positions) == 1
        assert momentum_module.scalping_positions[0]["code"] == "123456"
        assert "time_str" in momentum_module.scalping_positions[0]

    def test_check_momentum_outside_hours(self):
        """장 시간 외에는 로직 실행 안함"""
        with patch("src.trading.momentum.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 8 # 9시 이전

            with patch("src.trading.momentum.get_kis_client") as mock_client:
                check_momentum_and_scalp()
                mock_client.assert_not_called()

    def test_momentum_api_exception(self, mock_kis_client_for_momentum):
        """API 호출 중 에러 발생 시 처리"""
        # get_rank_rising 호출 시 에러 발생
        mock_kis_client_for_momentum.get_rank_rising.side_effect = Exception("API Error")

        with patch("src.trading.momentum.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 10
            # 예외가 발생해도 크래시 나지 않고 로그만 찍고 종료되어야 함
            check_momentum_and_scalp()
            # 호출은 되었으나 에러로 중단
            mock_kis_client_for_momentum.get_rank_rising.assert_called_once()
            # 매수 로직은 실행되지 않음
            mock_kis_client_for_momentum.buy_stock.assert_not_called()
