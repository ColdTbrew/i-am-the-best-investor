import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.trading.momentum import scalping_positions, sell_all_scalps, execute_momentum_buy
from src.utils.state import state


@pytest.mark.asyncio
async def test_check_momentum_sends_approval(mock_kis_client_for_momentum, clean_scalping_positions):
    """급등주 포착 시 즉시 매수 대신 디스코드 승인 요청을 보내는지 테스트"""
    from src.trading.momentum import check_momentum_and_scalp

    with patch("src.trading.momentum.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10
        mock_dt.now.return_value.strftime.return_value = "2023-01-01"

        with patch("src.trading.momentum.send_momentum_approval", new_callable=AsyncMock) as mock_approval:
            await check_momentum_and_scalp()

            # 승인 요청이 전송되어야 함
            mock_approval.assert_called_once()
            call_args = mock_approval.call_args[0]
            assert call_args[0] == "123456"  # code
            assert call_args[1] == "TestStock"  # name

            # 즉시 매수는 일어나면 안 됨
            mock_kis_client_for_momentum.buy_stock.assert_not_called()
            assert len(scalping_positions) == 0


@pytest.mark.asyncio
async def test_check_momentum_skip_conditions(mock_kis_client_for_momentum, clean_scalping_positions):
    """조건 불만족 시 매수 스킵 테스트"""
    from src.trading.momentum import check_momentum_and_scalp

    mock_kis_client_for_momentum.get_rank_rising.return_value = {
        "output": [
            {
                "stck_shrn_iscd": "111111",
                "hts_kor_isnm": "OverRisenStock",
                "prdy_ctrt": "25.0",  # 20% 초과 (위험)
                "acml_vol": "200000",
                "stck_prpr": "10000"
            },
            {
                "stck_shrn_iscd": "222222",
                "hts_kor_isnm": "LowVolStock",
                "prdy_ctrt": "10.0",
                "acml_vol": "1000",  # 거래량 부족
                "stck_prpr": "10000"
            }
        ]
    }

    with patch("src.trading.momentum.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10

        with patch("src.trading.momentum.send_momentum_approval", new_callable=AsyncMock) as mock_approval:
            await check_momentum_and_scalp()

            mock_approval.assert_not_called()
            mock_kis_client_for_momentum.buy_stock.assert_not_called()
            assert len(scalping_positions) == 0


@pytest.mark.asyncio
async def test_check_momentum_insufficient_balance(mock_kis_client_for_momentum, clean_scalping_positions):
    """잔액 부족 시 승인 요청 없이 경고 메시지 전송"""
    from src.trading.momentum import check_momentum_and_scalp

    # 잔액 0원으로 설정
    mock_kis_client_for_momentum.get_balance.return_value = {
        "output2": [{"dnca_tot_amt": "0"}]
    }

    with patch("src.trading.momentum.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10
        mock_dt.now.return_value.strftime.return_value = "2023-01-01"

        with patch("src.trading.momentum.send_momentum_approval", new_callable=AsyncMock) as mock_approval:
            with patch("src.trading.momentum.send_webhook_message") as mock_webhook:
                await check_momentum_and_scalp()

                # 승인 요청 없어야 함
                mock_approval.assert_not_called()
                # 경고 웹훅 메시지 전송되어야 함
                mock_webhook.assert_called_once()
                assert "잔액 부족" in mock_webhook.call_args[0][0]


def test_execute_momentum_buy_success(mock_kis_client_for_momentum, clean_scalping_positions):
    """execute_momentum_buy 성공 시 포지션 추가 확인"""
    res = execute_momentum_buy("123456", "TestStock", 10, 10000)

    assert res.get("rt_cd") == "0"
    assert len(scalping_positions) == 1
    assert scalping_positions[0]["code"] == "123456"
    assert scalping_positions[0]["qty"] == 10


def test_sell_all_scalps(mock_kis_client_for_momentum, clean_scalping_positions):
    """일괄 매도 테스트"""
    scalping_positions.append({
        "code": "123456",
        "name": "TestStock",
        "qty": 10,
        "buy_price": 10000
    })

    sell_all_scalps()

    mock_kis_client_for_momentum.sell_stock.assert_called_once_with("123456", 10)
    assert len(scalping_positions) == 0
