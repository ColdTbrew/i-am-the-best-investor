# CLAUDE.md

## Project Overview

LLM-powered automatic stock trading bot for Korean stocks (한국투자증권 API).
Runs daily at market open (09:00 KST), uses OpenAI GPT to analyze market data and execute buy/sell decisions.

## Tech Stack

- **Language:** Python 3.11+
- **Package Manager:** uv
- **LLM:** OpenAI API (gpt-5-nano)
- **Trading API:** Korea Investment Open API
- **Discord:** discord.py for interactive commands and webhook notifications
- **ML:** torch, transformers, chronos-forecasting for price prediction
- **Data:** pandas, pykrx, feedparser, beautifulsoup4, playwright

## Common Commands

```bash
# Install dependencies
uv sync

# Run the bot (scheduler mode)
uv run python main.py

# Run with Discord bot
uv run python main.py --discord-bot
uv run python main.py --with-discord    # scheduler + discord

# Manual routines
uv run python main.py --morning
uv run python main.py --evening

# CLI trading
uv run python main.py --action buy --code 005930 --qty 10
uv run python main.py --mode paper      # paper trading mode

# Lint
uv run ruff check .
uv run ruff check --fix .

# Tests (requires env vars or will fail at import time)
PYTHONPATH=. uv run pytest src/tests/
```

## Project Structure

```
src/
  analysis/       - LLM analysis engine (llm_analyzer.py, price_predictor.py)
  trading/        - KIS API client and momentum/scalping strategy
  data/           - News fetching, stock screening, article extraction, chart generation
  scheduler/      - Daily job scheduling and morning/evening routines
  utils/          - Config, logger, Discord bot, state management, favorites
  tests/          - pytest test suite
main.py           - Entry point with CLI argument parsing
```

## Architecture Notes

- All source imports use absolute paths from project root: `from src.module.submodule import ...`
- Tests require `PYTHONPATH=.` to resolve `src.*` imports
- Tests also require environment variables (OpenAI API key, KIS credentials) because modules initialize API clients at import time. Without a `.env` file, tests will fail with import errors.
- No ruff or pytest config in `pyproject.toml` beyond dependency declarations — default settings are used.
- The Discord bot (`src/utils/discord_bot.py`) is the largest module (~999 lines) with slash commands.

## Environment Variables

Required in `.env` (see `.env.example`):
- `TRADING_MODE` — `paper` or `real`
- `real_account_api_key`, `real_account_api_secret`, `real_account_number`
- `fake_account_api_key`, `fake_account_api_secret`, `fake_account_number`
- `openai_api_key`
- `DISCORD_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`

## Risk Config

Defined in `src/utils/config.py`:
- Max 3 buy orders/day, max 20% per stock position
- Buy range: 100K–5M KRW, default 1M KRW per stock
- Stop loss: -5%, Take profit: +15%, Max daily loss: -3%
- Scalping amount: 100K KRW

## Deployment

Docker support via `Dockerfile` and `docker-compose.yml` (Python 3.12-slim, Playwright, Korean fonts).
