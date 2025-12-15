# Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# uv 설치
RUN pip install uv

# 의존성 파일 복사
COPY pyproject.toml uv.lock* ./

# 의존성 설치
RUN uv sync --frozen --no-dev

# 소스 코드 복사
COPY . .

# 환경변수 설정
ENV TRADING_MODE=paper

# 실행 (스케줄러 + Discord 봇)
CMD ["uv", "run", "python", "main.py", "--with-discord"]
