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

# 한글 폰트 설정 (Linux: NanumGothic)
plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False


def generate_stock_chart(stock_code: str, stock_name: str, days: int = 7, 
                         prediction_data: dict = None) -> str:
    """
    종목의 최근 N일 주가 차트 및 예측 데이터 시각화
    
    Args:
        stock_code: 종목코드
        stock_name: 종목명
        days: 조회 기간
        prediction_data: { 'bull_case': [], 'bear_case': [], 'median': [] }
    """
    try:
        # 날짜 범위 계산
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10) # 1개월 요청시 30일
        
        # 주가 데이터 조회
        df = pykrx_stock.get_market_ohlcv(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            stock_code
        )
        
        if df.empty:
            logger.warning(f"{stock_name} 차트 데이터 없음")
            return None
        
        # 최근 N개 영업일 데이터 사용
        df = df.tail(days)
        dates = df.index.to_list()
        prices = df['종가'].to_list()
        
        # 차트 생성
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # 1. 과거 데이터 플롯
        color = '#00B8D9' # 기본 파란색 계열
        ax.plot(dates, prices, color=color, linewidth=2, label='과거 주가')
        ax.fill_between(dates, prices, alpha=0.1, color=color)
        
        # 2. 예측 데이터 플롯 (있을 경우)
        if prediction_data:
            last_date = dates[-1]
            last_price = prices[-1]
            
            # 예측 날짜 생성 (평일 기준은 복잡하므로 단순 날짜로 처리하거나 평일 필터링)
            pred_dates = []
            curr = last_date
            while len(pred_dates) < 3:
                curr += timedelta(days=1)
                # 0:월, 1:화, ..., 4:금, 5:토, 6:일
                if curr.weekday() < 5:
                    pred_dates.append(curr)
            
            # Bull Case (상승)
            bull_prices = [last_price] + prediction_data['bull_case']
            bull_dates = [last_date] + pred_dates
            ax.plot(bull_dates, bull_prices, color='#FF8A65', linestyle='--', linewidth=2, label='Bull (90%)')
            
            # Bear Case (하락)
            bear_prices = [last_price] + prediction_data['bear_case']
            bear_dates = [last_date] + pred_dates
            ax.plot(bear_dates, bear_prices, color='#4DB6AC', linestyle='--', linewidth=2, label='Bear (10%)')
            
            # 영역 채우기
            ax.fill_between(bull_dates, bear_prices, bull_prices, color='gray', alpha=0.05)
            
            # Y축 범위 조정 (예측 범위가 잘 보이도록)
            all_prices = prices + prediction_data['bull_case'] + prediction_data['bear_case']
            min_p = min(all_prices)
            max_p = max(all_prices)
            padding = (max_p - min_p) * 0.15 # 15% 여백
            ax.set_ylim(min_p - padding, max_p + padding)
            
            # x축 확장
            ax.set_xlim(dates[0], pred_dates[-1] + timedelta(days=1))
        else:
            # 일반 차트 Y축 여백
            min_p = min(prices)
            max_p = max(prices)
            padding = (max_p - min_p) * 0.1
            ax.set_ylim(min_p - padding, max_p + padding)

        # 스타일링
        ax.set_title(f'📊 {stock_name} ({stock_code}) 분석 및 예측', fontsize=14, fontweight='bold', pad=15)
        ax.set_ylabel('가격 (원)' if len(stock_code) == 6 else 'Price ($)')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.grid(True, alpha=0.2)
        ax.legend(loc='upper left', fontsize=9)
        
        # 현재가 표시
        end_price = prices[-1]
        ax.annotate(
            f'{end_price:,.0f}' if len(stock_code) == 6 else f'${end_price:,.2f}',
            xy=(dates[-1], end_price),
            xytext=(5, 5),
            textcoords='offset points',
            fontsize=10,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', fc='yellow', alpha=0.3)
        )
        
        plt.tight_layout()
        
        # 임시 파일로 저장
        temp_dir = Path(tempfile.gettempdir()) / "stock_charts"
        temp_dir.mkdir(exist_ok=True)
        
        chart_path = temp_dir / f"{stock_code}_pred_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close(fig)
        
        return str(chart_path)
        
    except Exception as e:
        logger.error(f"차트 생성 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
