import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
import src.trading.momentum as momentum_module
from src.trading.momentum import load_state, save_state, check_momentum_and_scalp


class TestMomentumExtended:

    def test_load_save_state(self, tmp_path, monkeypatch):
        """상태 저장 및 로드 테스트"""
        state_file = tmp_path / "scalping_state.json"
        monkeypatch.setattr("src.trading.momentum.STATE_FILE", state_file)

        now = datetime.now()
        test_pos = {
            "code": "123456",
            "name": "SaveTest",
            "qty": 10,
            "buy_price": 1000,
            "time": now
        }
        momentum_module.scalping_positions.append(test_pos)
        save_state()

        assert state_file.exists()

        momentum_module.scalping_positions.clear()
        load_state()

        assert len(momentum_module.scalping_positions) == 1
        assert momentum_module.scalping_positions[0]["code"] == "123456"
        assert "time_str" in momentum_module.scalping_positions[0]

        # 정리
        momentum_module.scalping_positions.clear()

    @pytest.mark.asyncio
    async def test_check_momentum_outside_hours(self):
        """장 시간 외에는 로직 실행 안함"""
        with patch("src.trading.momentum.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 8  # 9시 이전

            with patch("src.trading.momentum.get_kis_client") as mock_client:
                await check_momentum_and_scalp()
                mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_momentum_api_exception(self, mock_kis_client_for_momentum):
        """API 호출 중 에러 발생 시 처리"""
        mock_kis_client_for_momentum.get_rank_rising.side_effect = Exception("API Error")

        with patch("src.trading.momentum.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 10

            with patch("src.trading.momentum.send_momentum_approval", new_callable=AsyncMock) as mock_approval:
                await check_momentum_and_scalp()

                # 랭킹 조회 실패 → 승인 요청 없어야 함
                mock_approval.assert_not_called()
                mock_kis_client_for_momentum.buy_stock.assert_not_called()

    @pytest.mark.asyncio
    async def test_momentum_zero_quantity(self, mock_kis_client_for_momentum, clean_scalping_positions):
        """현재가가 너무 높아 수량이 0이 되는 경우"""
        # 현재가를 scalping_amount보다 훨씬 높게 설정
        mock_kis_client_for_momentum.get_rank_rising.return_value = {
            "output": [
                {
                    "stck_shrn_iscd": "123456",
                    "hts_kor_isnm": "ExpensiveStock",
                    "prdy_ctrt": "10.0",
                    "acml_vol": "200000",
                    "stck_prpr": "99999999"  # 1억원짜리 주식
                }
            ]
        }

        with patch("src.trading.momentum.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 10
            mock_dt.now.return_value.strftime.return_value = "2023-01-01"

            with patch("src.trading.momentum.send_momentum_approval", new_callable=AsyncMock) as mock_approval:
                with patch("src.trading.momentum.send_webhook_message") as mock_webhook:
                    await check_momentum_and_scalp()

                    # 수량 0이므로 승인 요청 없어야 함
                    mock_approval.assert_not_called()
                    # 경고 메시지 전송
                    mock_webhook.assert_called()
                    assert "수량 부족" in mock_webhook.call_args[0][0]
