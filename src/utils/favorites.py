import json
import os
import asyncio
import copy
from typing import List, Dict, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_FAVORITES_FILE = "favorites.json"

class FavoritesManager:
    def __init__(self, filename: str = DEFAULT_FAVORITES_FILE):
        self.filename = filename
        self.favorites = {}
        # Lock for file writing serialization
        self._lock = asyncio.Lock()

        # We can't await in __init__, so we'll load synchronously or lazily.
        # Since this is a small file, synchronous load on startup is fine.
        # But writes should be async if possible or threaded.
        self._load_favorites_sync()

    def _load_favorites_sync(self):
        """Synchronous load for initialization."""
        if not os.path.exists(self.filename):
            self.favorites = {}
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.favorites = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load favorites: {e}")
            self.favorites = {}

    async def _save_favorites_async(self):
        """Save favorites asynchronously using a thread executor, serialized with a lock."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            # Create a deep copy to ensure thread safety during json.dump
            # self.favorites might be modified in the main loop while json.dump is running in the thread.
            data_snapshot = copy.deepcopy(self.favorites)
            await loop.run_in_executor(None, self._save_favorites_sync, data_snapshot)

    def _save_favorites_sync(self, data: Dict):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save favorites: {e}")

    async def add_favorite(self, user_id: int, stock_info: Dict) -> bool:
        """Add a stock to favorites. Returns True if added, False if already exists."""
        user_key = str(user_id)
        if user_key not in self.favorites:
            self.favorites[user_key] = []

        # Check if already exists
        for item in self.favorites[user_key]:
            if item["code"] == stock_info["code"]:
                return False

        self.favorites[user_key].append(stock_info)
        await self._save_favorites_async()
        return True

    async def remove_favorite(self, user_id: int, stock_code: str) -> bool:
        """Remove a stock from favorites. Returns True if removed, False if not found."""
        user_key = str(user_id)
        if user_key not in self.favorites:
            return False

        initial_len = len(self.favorites[user_key])
        self.favorites[user_key] = [item for item in self.favorites[user_key] if item["code"] != stock_code]

        if len(self.favorites[user_key]) < initial_len:
            await self._save_favorites_async()
            return True
        return False

    def get_favorites(self, user_id: int) -> List[Dict]:
        """Get list of favorites for a user. Returns a copy to prevent external mutation affecting internal state."""
        return copy.deepcopy(self.favorites.get(str(user_id), []))

favorites_manager = FavoritesManager()
