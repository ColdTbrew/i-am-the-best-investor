import asyncio
import os
from datetime import datetime, timedelta
from src.data import generate_stock_chart
from src.analysis.price_predictor import predictor
from src.trading import get_kis_client
from pykrx import stock as pykrx_stock
import pytest

@pytest.mark.asyncio
async def test_prediction_and_chart():
    print("🚀 예측 및 차트 생성 테스트 시작...")
    
    # 1. 테스트 종목 (삼성전자)
    stock_code = "005930"
    stock_name = "삼성전자"
    
    # 2. 데이터 수집
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    print(f"📊 {stock_name} 데이터 수집 중...")
    df = pykrx_stock.get_market_ohlcv(
        start_date.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d"),
        stock_code
    )
    
    if df.empty:
        print("❌ 데이터 수집 실패")
        return
    
    prices = df['종가'].tail(30).to_list()
    print(f"✅ 데이터 수집 완료 (데이터 수: {len(prices)})")
    
    # 3. 예측 수행
    print("🔮 Chronos-Tiny 예측 수행 중...")
    prediction = predictor.predict_3day_trend(prices)
    
    if not prediction:
        print("❌ 예측 실패")
        return
    
    print(f"✅ 예측 결과:")
    print(f"  - Bull Case: {[round(p) for p in prediction['bull_case']]}")
    print(f"  - Bear Case: {[round(p) for p in prediction['bear_case']]}")
    
    # 4. 차트 생성
    print("🎨 차트 생성 중...")
    chart_path = generate_stock_chart(stock_code, stock_name, days=30, prediction_data=prediction)
    
    if chart_path and os.path.exists(chart_path):
        print(f"✅ 차트 생성 성공: {chart_path}")
    else:
        print("❌ 차트 생성 실패")

if __name__ == "__main__":
    asyncio.run(test_prediction_and_chart())
