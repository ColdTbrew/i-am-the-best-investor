import torch
import time
import psutil
import os
import numpy as np
from chronos import ChronosPipeline
from pykrx import stock as pykrx_stock
from datetime import datetime, timedelta

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

def benchmark_model(model_id, prices):
    print(f"\n--- Model: {model_id} ---")
    
    # 1. 로딩 전 메모리
    mem_before = get_memory_usage()
    
    # 2. 모델 로드 시간 측정
    start_load = time.time()
    pipeline = ChronosPipeline.from_pretrained(
        model_id,
        device_map="cpu",
        torch_dtype=torch.float32,
    )
    load_time = time.time() - start_load
    mem_after_load = get_memory_usage()
    
    # 3. 추론 시간 및 예측값 측정
    context = torch.tensor(prices, dtype=torch.float32)
    start_inf = time.time()
    forecast = pipeline.predict(context, 3)
    inference_time = time.time() - start_inf
    mem_after_inf = get_memory_usage()
    
    # 4. 결과 정리
    samples = forecast[0].numpy()
    bull = np.quantile(samples, 0.9, axis=0)
    bear = np.quantile(samples, 0.1, axis=0)
    median = np.quantile(samples, 0.5, axis=0)
    
    print(f"로딩 시간: {load_time:.2f}s")
    print(f"추론 시간: {inference_time:.2f}s")
    print(f"메모리 증가 (로드): {mem_after_load - mem_before:.2f}MB")
    print(f"최종 메모리 사용량: {mem_after_inf:.2f}MB")
    print(f"예측 결과 (Median): {[round(p, 2) for p in median.tolist()]}")
    print(f"예측 범위 (Bear-Bull): {[round(p, 2) for p in bear.tolist()]} ~ {[round(p, 2) for p in bull.tolist()]}")
    
    return {
        "load_time": load_time,
        "inference_time": inference_time,
        "mem_usage": mem_after_inf - mem_before,
        "median": median.tolist()
    }

def run_benchmark():
    # 데이터 준비 (삼성전자 최근 30일)
    print("⏳ 데이터 수집 중...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    df = pykrx_stock.get_market_ohlcv(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"), "005930")
    prices = df['종가'].tail(30).to_list()
    print(f"✅ 데이터 준비 완료 (현재가: {prices[-1]:,}원)")

    # Tiny 벤치마크
    tiny_res = benchmark_model("amazon/chronos-t5-tiny", prices)
    
    # 메모리 정리를 위해 파이프라인 삭제 (추측성)
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    
    # Small 벤치마크
    small_res = benchmark_model("amazon/chronos-t5-small", prices)

    print("\n" + "="*40)
    print("📊 최종 비교 결과 (Small vs Tiny)")
    print(f"속도 차이 (추론): {small_res['inference_time'] / tiny_res['inference_time']:.1f}배 느림")
    print(f"메모리 차이: {small_res['mem_usage'] - tiny_res['mem_usage']:.1f}MB 추가 사용")
    
    # 예측값 차이 (마지막 날 기준)
    diff = abs(small_res['median'][-1] - tiny_res['median'][-1]) / tiny_res['median'][-1] * 100
    print(f"예측값 차이 (3일째): {diff:.2f}%")

if __name__ == "__main__":
    run_benchmark()
