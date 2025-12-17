import pytest
from unittest.mock import MagicMock, patch
from src.trading.momentum import check_momentum_and_scalp, scalping_positions, sell_all_scalps
from src.utils.state import state

def test_check_momentum_buy(mock_kis_client_for_momentum, clean_scalping_positions):
    """급등주 포착 및 매수 로직 테스트"""
    # 시간 모킹 (장중 10시)
    with patch("src.trading.momentum.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10
        mock_dt.now.return_value.strftime.return_value = "2023-01-01"

        check_momentum_and_scalp()

        # 매수 확인
        assert len(scalping_positions) == 1
        assert scalping_positions[0]["code"] == "123456"
        assert scalping_positions[0]["name"] == "TestStock"

        # API 호출 확인
        mock_kis_client_for_momentum.buy_stock.assert_called_once()
        args = mock_kis_client_for_momentum.buy_stock.call_args[0]
        assert args[0] == "123456"

def test_check_momentum_skip_conditions(mock_kis_client_for_momentum, clean_scalping_positions):
    """조건 불만족 시 매수 스킵 테스트"""
    # 상한가(30%) or 거래량 부족 등으로 데이터 변경
    mock_kis_client_for_momentum.get_rank_rising.return_value = {
        "output": [
            {
                "stck_shrn_iscd": "111111",
                "prdy_ctrt": "25.0", # 20% 초과 (위험)
                "acml_vol": "200000",
                "stck_prpr": "10000"
            },
            {
                "stck_shrn_iscd": "222222",
                "prdy_ctrt": "10.0",
                "acml_vol": "1000", # 거래량 부족
                "stck_prpr": "10000"
            }
        ]
    }

    with patch("src.trading.momentum.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10
        check_momentum_and_scalp()

        assert len(scalping_positions) == 0
        mock_kis_client_for_momentum.buy_stock.assert_not_called()

def test_sell_all_scalps(mock_kis_client_for_momentum, clean_scalping_positions):
    """일괄 매도 테스트"""
    # 가상의 보유 포지션 추가
    scalping_positions.append({
        "code": "123456",
        "name": "TestStock",
        "qty": 10,
        "buy_price": 10000
    })

    sell_all_scalps()

    # 매도 호출 확인
    mock_kis_client_for_momentum.sell_stock.assert_called_once_with("123456", 10)
    # 리스트 비워졌는지 확인
    assert len(scalping_positions) == 0
