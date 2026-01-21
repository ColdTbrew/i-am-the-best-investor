import torch
import pandas as pd
import numpy as np
from chronos import ChronosPipeline
from src.utils.logger import get_logger

logger = get_logger(__name__)

class PricePredictor:
    """Amazon Chronos-Small를 이용한 주가 예측 엔진"""
    
    def __init__(self, model_id: str = "amazon/chronos-t5-small", device: str = "cpu"):
        logger.info(f"Chronos 모델 로드 중: {model_id} (Device: {device})")
        try:
            self.pipeline = ChronosPipeline.from_pretrained(
                model_id,
                device_map=device,
                torch_dtype=torch.float32,
            )
            logger.info("Chronos 모델 로드 완료")
        except Exception as e:
            logger.error(f"Chronos 모델 로드 실패: {e}")
            self.pipeline = None

    def predict_3day_trend(self, prices: list) -> dict:
        """
        최근 주가 데이터를 기반으로 향후 3일간의 예측 수행
        
        Args:
            prices: 최근 주가 리스트 (최소 10개 이상 권장)
            
        Returns:
            dict: {
                'bull_case': [p1, p2, p3], # 90분위수
                'bear_case': [p1, p2, p3], # 10분위수
                'median': [p1, p2, p3]     # 50분위수
            }
        """
        if not self.pipeline or not prices or len(prices) < 2:
            return None
        
        try:
            # 텐서 변환
            context = torch.tensor(prices, dtype=torch.float32)
            
            # 예측 수행 (3일치)
            prediction_length = 3
            forecast = self.pipeline.predict(context, prediction_length)
            
            # 분위수별 값 추출 (Bull: 90%, Bear: 10%, Median: 50%)
            # Chronos output shape: (num_series, prediction_length, num_samples)
            # or (prediction_length, num_samples) depending on input
            
            # forecast는 보통 (num_samples, prediction_length) 형태의 텐서 리스트임
            # 0.2.x 버전 기준: [tensor(num_samples, prediction_length)]
            samples = forecast[0].numpy() # (num_samples, 3)
            
            bull = np.quantile(samples, 0.9, axis=0)
            bear = np.quantile(samples, 0.1, axis=0)
            median = np.quantile(samples, 0.5, axis=0)
            
            return {
                "bull_case": bull.tolist(),
                "bear_case": bear.tolist(),
                "median": median.tolist()
            }
        except Exception as e:
            logger.error(f"주가 예측 중 에러: {e}")
            return None

# 싱글톤 인스턴스
predictor = PricePredictor()
