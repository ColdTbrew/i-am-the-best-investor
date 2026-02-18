FROM python:3.12-slim

WORKDIR /app

# 타임존 설정 (Asia/Seoul)
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 시스템 패키지 설치 (Playwright, 한글 폰트 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-nanum \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/matplotlib/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 프로젝트 파일 복사
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY main.py .
COPY favorites.json* ./

# 의존성 설치
RUN uv sync --frozen --no-dev

# Playwright 브라우저 설치
RUN uv run playwright install chromium

# 실행
CMD ["uv", "run", "main.py", "--with-discord"]
