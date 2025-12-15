import pytest
from src.utils.state import state
from src.trading.kis_client import get_kis_client

def test_global_state_mode():
    state.set_mode("paper")
    assert state.get_mode() == "paper"
    state.set_mode("real")
    assert state.get_mode() == "real"
    state.set_mode("invalid")
    assert state.get_mode() == "real"  # Should not change

def test_kis_client_singleton_multimode():
    # Setup
    state.set_mode("paper")

    # Check default (paper)
    client_paper = get_kis_client()
    assert client_paper.mode == "paper"

    # Check explicit real
    client_real = get_kis_client("real")
    assert client_real.mode == "real"

    # Ensure they are distinct instances
    assert client_paper is not client_real

    # Check singleton property
    client_paper_2 = get_kis_client("paper")
    assert client_paper is client_paper_2

def test_trading_config_loading():
    from src.utils.config import KIS_CONFIG
    assert "real" in KIS_CONFIG
    assert "paper" in KIS_CONFIG
