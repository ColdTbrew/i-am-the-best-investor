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
| `/portfolio` | 포트폴리오 조회 |
| `/analyze 삼성전자` | 종목 분석 (한국/미국) |
| `/news` | 최신 뉴스 |
| `/stop` | 거래 중지 |
| `/resume` | 거래 재개 |

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

## 🐳 Docker 배포

```bash
docker build -t trading-bot .
docker run -d --env-file .env --restart=always trading-bot
```

## ⚠️ 면책사항

이 프로그램으로 인한 투자 손실에 대해 책임지지 않습니다.
투자는 본인 판단과 책임하에 진행하세요.

## 📄 라이선스

MIT License
