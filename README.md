# 🤖 LLM 기반 자동매매 봇

LLM(GPT)을 활용한 한국 주식 자동매매 봇입니다.

## ✨ 주요 기능

- 🧠 **LLM 분석**: OpenAI GPT가 시장 분석 및 매수/매도 판단
- 📈 **자동 거래**: 한국투자증권 API로 자동 주문 실행
- 📰 **뉴스 수집**: RSS 기반 실시간 뉴스 분석
- 💬 **Discord 연동**: 슬래시 명령어 + 실시간 알림
- 🎯 **확신도 기반 투자**: LLM 확신도에 따라 투자 금액 조절

## 🚀 시작하기

### 1. 의존성 설치

```bash
# uv 사용 (권장)
uv sync

# 또는 pip
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 복사하여 `.env` 생성:

```bash
cp .env.example .env
```

필요한 API 키 설정:
- 한국투자증권 Open API
- OpenAI API
- Discord Bot Token

### 3. 실행

```bash
# 스케줄러 모드 (매일 08:30 자동 실행)
uv run python main.py

# 즉시 실행 (테스트)
uv run python main.py --run-now

# Discord 봇 모드
uv run python main.py --discord-bot

# 스케줄러 + Discord
uv run python main.py --with-discord
```

## 📱 Discord 명령어

| 명령어 | 설명 |
|--------|------|
| `/status` | 봇 상태 확인 |
| `/mode` | 거래 모드 변경 (Real / Paper) |
| `/portfolio` | 포트폴리오 조회 |
| `/analyze 삼성전자` | 종목 분석 (한국/미국) |
| `/morning` | 🌅 아침 루틴 즉시 실행 (한국장) |
| `/evening` | 🌙 저녁 루틴 즉시 실행 (미국장) |
| `/news` | 최신 뉴스 |
| `/buy 삼성전자 10` | 매수 주문 |
| `/sell 삼성전자 10` | 매도 주문 |

## ⚙️ 설정

`src/utils/config.py`에서 리스크 관리 설정:

```python
RISK_CONFIG = {
    "max_buy_per_day": 3,           # 하루 최대 3종목
    "min_buy_amount": 100000,       # 최소 10만원
    "max_buy_amount": 5000000,      # 최대 500만원
    "buy_amount_per_stock": 1000000,# 기본 100만원
    "stop_loss_rate": -0.05,        # 손절 -5%
    "take_profit_rate": 0.15,       # 익절 +15%
}
```

## 🐳 Docker 배포 (Oracle VM / Ubuntu)

### 1. VM 초기 설정

```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# Docker 설치
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker

# Git, Vim 설치
sudo apt install -y git vim
```

### 2. 코드 클론

```bash
git clone https://github.com/<your-username>/i-am-the-best-investor.git
cd i-am-the-best-investor
```

### 3. 환경변수 설정

```bash
cp .env.example .env
vi .env  # API 키 입력
```

### 4. Docker 빌드 & 실행

```bash
# 이미지 빌드
docker build -t trading-bot .

# 컨테이너 실행 (백그라운드, 자동 재시작)
docker run -d \
  --name trading-bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  trading-bot
```

### 5. 관리 명령어

```bash
# 로그 확인
docker logs -f trading-bot

# 상태 확인
docker ps

# 중지/시작/재시작
docker stop trading-bot
docker start trading-bot
docker restart trading-bot

# 컨테이너 삭제 후 재빌드
docker rm -f trading-bot
docker build -t trading-bot .
```

## ⚠️ 면책사항

이 프로그램으로 인한 투자 손실에 대해 책임지지 않습니다.
투자는 본인 판단과 책임하에 진행하세요.

## 📄 라이선스

MIT License
