"""뉴스 데이터 수집 모듈"""
import feedparser
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)

# RSS 피드 소스 (API 키 불필요)
NEWS_SOURCES = {
    "google_stock": "https://news.google.com/rss/search?q=주식+코스피&hl=ko&gl=KR&ceid=KR:ko",
    "google_economy": "https://news.google.com/rss/search?q=경제+증시&hl=ko&gl=KR&ceid=KR:ko",
    "hankyung": "https://www.hankyung.com/feed/stock",
}


@dataclass
class NewsItem:
    """뉴스 아이템"""
    title: str
    link: str
    source: str
    published: Optional[datetime] = None
    summary: str = ""


def fetch_news(max_items: int = 20) -> list[dict]:
    """
    여러 소스에서 뉴스 수집
    
    Args:
        max_items: 최대 수집 개수
    
    Returns:
        뉴스 리스트 (dict 형태)
    """
    all_news = []
    
    for source_name, rss_url in NEWS_SOURCES.items():
        try:
            news = _fetch_from_rss(rss_url, source_name)
            all_news.extend(news)
            logger.info(f"{source_name}에서 {len(news)}개 뉴스 수집")
        except Exception as e:
            logger.warning(f"{source_name} 뉴스 수집 실패: {e}")
    
    # 중복 제거 (제목 기준)
    seen_titles = set()
    unique_news = []
    for item in all_news:
        if item["title"] not in seen_titles:
            seen_titles.add(item["title"])
            unique_news.append(item)
    
    # 최신순 정렬 및 개수 제한
    unique_news = sorted(
        unique_news, 
        key=lambda x: x.get("published", ""), 
        reverse=True
    )[:max_items]
    
    logger.info(f"총 {len(unique_news)}개 뉴스 수집 완료")
    return unique_news


def _fetch_from_rss(rss_url: str, source_name: str) -> list[dict]:
    """RSS 피드에서 뉴스 수집"""
    feed = feedparser.parse(rss_url)
    
    news_list = []
    for entry in feed.entries[:10]:  # 소스당 최대 10개
        # 발행일 파싱
        published = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except:
                pass
        
        news_list.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "source": source_name,
            "published": published.isoformat() if published else "",
            "summary": entry.get("summary", "")[:200],  # 요약 200자 제한
        })
    
    return news_list


def search_stock_news(stock_name: str, max_items: int = 5) -> list[dict]:
    """
    특정 종목 관련 뉴스 검색
    
    Args:
        stock_name: 종목명 (예: "삼성전자")
        max_items: 최대 수집 개수
    
    Returns:
        뉴스 리스트
    """
    # Google News에서 종목명으로 검색
    search_url = f"https://news.google.com/rss/search?q={stock_name}&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        news = _fetch_from_rss(search_url, f"google_{stock_name}")
        logger.info(f"{stock_name} 관련 뉴스 {len(news)}개 수집")
        return news[:max_items]
    except Exception as e:
        logger.warning(f"{stock_name} 뉴스 검색 실패: {e}")
        return []
