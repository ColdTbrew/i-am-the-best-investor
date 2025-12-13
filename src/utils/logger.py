"""LLM 기반 자동매매 봇 - 로깅 설정"""
import sys
from pathlib import Path
from loguru import logger

# 로그 디렉토리
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 기본 로거 제거 후 재설정
logger.remove()

# 콘솔 출력
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)

# 파일 출력 (일별 로테이션)
logger.add(
    LOG_DIR / "trading_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
)

# 에러 전용 로그
logger.add(
    LOG_DIR / "error_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    level="ERROR",
    rotation="00:00",
    retention="30 days",
)


def get_logger(name: str):
    """모듈별 로거 반환"""
    return logger.bind(name=name)
