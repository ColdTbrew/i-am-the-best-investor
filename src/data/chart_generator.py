"""주가 차트 생성기"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # 서버 환경용 백엔드
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pykrx import stock as pykrx_stock

from src.utils.logger import get_logger

logger = get_logger(__name__)

# 한글 폰트 설정 (macOS)
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False


def generate_stock_chart(stock_code: str, stock_name: str, days: int = 7) -> str:
    """
    종목의 최근 N일 주가 차트 생성
    
    Args:
        stock_code: 종목코드 (6자리)
        stock_name: 종목명
        days: 조회 기간 (기본 7일)
    
    Returns:
        생성된 차트 이미지 파일 경로
    """
    try:
        # 날짜 범위 계산
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 5)  # 휴장일 감안 여유
        
        # pykrx로 OHLCV 데이터 조회
        df = pykrx_stock.get_market_ohlcv(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            stock_code
        )
        
        if df.empty:
            logger.warning(f"{stock_name} 차트 데이터 없음")
            return None
        
        # 최근 N일만 사용
        df = df.tail(days)
        
        # 차트 생성
        fig, ax = plt.subplots(figsize=(8, 4))
        
        # 종가 라인 차트
        dates = df.index
        prices = df['종가']
        
        # 상승/하락 색상
        color = '#00D084' if prices.iloc[-1] >= prices.iloc[0] else '#FF6B6B'
        
        ax.plot(dates, prices, color=color, linewidth=2)
        ax.fill_between(dates, prices, alpha=0.2, color=color)
        
        # 스타일링
        ax.set_title(f'{stock_name} ({stock_code}) - {days}일 차트', fontsize=12, fontweight='bold')
        ax.set_ylabel('가격 (원)')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.grid(True, alpha=0.3)
        
        # 시작/종료 가격 표시
        start_price = prices.iloc[0]
        end_price = prices.iloc[-1]
        change = end_price - start_price
        change_pct = (change / start_price) * 100
        
        ax.annotate(
            f'{end_price:,.0f}원 ({change_pct:+.1f}%)',
            xy=(dates[-1], end_price),
            xytext=(10, 0),
            textcoords='offset points',
            fontsize=10,
            color=color,
            fontweight='bold'
        )
        
        plt.tight_layout()
        
        # 임시 파일로 저장
        temp_dir = Path(tempfile.gettempdir()) / "stock_charts"
        temp_dir.mkdir(exist_ok=True)
        
        chart_path = temp_dir / f"{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"차트 생성 완료: {chart_path}")
        return str(chart_path)
        
    except Exception as e:
        logger.error(f"차트 생성 실패: {e}")
        return None
