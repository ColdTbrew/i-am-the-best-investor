import pytest
import os
import json
import asyncio
from src.utils.favorites import FavoritesManager

@pytest.fixture
def temp_favorites_file(tmp_path):
    # Create a temporary file path
    return tmp_path / "test_favorites.json"

@pytest.mark.asyncio
async def test_add_favorite(temp_favorites_file):
    manager = FavoritesManager(filename=str(temp_favorites_file))
    user_id = 12345
    stock_info = {"code": "005930", "name": "삼성전자", "market": "KR"}

    # Add
    assert await manager.add_favorite(user_id, stock_info) is True

    # Check persistence
    with open(temp_favorites_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert str(user_id) in data
        assert len(data[str(user_id)]) == 1
        assert data[str(user_id)][0]["code"] == "005930"

    # Add duplicate
    assert await manager.add_favorite(user_id, stock_info) is False

@pytest.mark.asyncio
async def test_remove_favorite(temp_favorites_file):
    manager = FavoritesManager(filename=str(temp_favorites_file))
    user_id = 12345
    stock_info = {"code": "005930", "name": "삼성전자", "market": "KR"}
    await manager.add_favorite(user_id, stock_info)

    # Remove
    assert await manager.remove_favorite(user_id, "005930") is True

    # Check empty
    assert len(manager.get_favorites(user_id)) == 0

    # Remove non-existent
    assert await manager.remove_favorite(user_id, "005930") is False

@pytest.mark.asyncio
async def test_multiple_users(temp_favorites_file):
    manager = FavoritesManager(filename=str(temp_favorites_file))
    user1 = 1
    user2 = 2
    stock1 = {"code": "005930", "name": "삼성전자"}
    stock2 = {"code": "AAPL", "name": "애플"}

    await manager.add_favorite(user1, stock1)
    await manager.add_favorite(user2, stock2)

    favs1 = manager.get_favorites(user1)
    favs2 = manager.get_favorites(user2)

    assert len(favs1) == 1
    assert favs1[0]["code"] == "005930"

    assert len(favs2) == 1
    assert favs2[0]["code"] == "AAPL"
