"""뉴스 기사 본문 추출 모듈 (Playwright headless browser)"""
import asyncio
from typing import Optional

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Playwright 지연 로딩 (설치 안 되어있을 경우 대비)
_playwright = None
_browser = None


async def get_browser():
    """Playwright 브라우저 인스턴스 가져오기 (싱글톤)"""
    global _playwright, _browser
    
    if _browser is None:
        try:
            from playwright.async_api import async_playwright
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(headless=True)
            logger.info("Playwright 브라우저 초기화 완료")
        except Exception as e:
            logger.error(f"Playwright 브라우저 초기화 실패: {e}")
            return None
    
    return _browser


async def extract_article_content(url: str, max_chars: int = 500, timeout: int = 10000) -> str:
    """
    URL에서 기사 본문 추출
    
    Args:
        url: 기사 URL
        max_chars: 최대 추출 문자 수
        timeout: 페이지 로드 타임아웃 (ms)
    
    Returns:
        추출된 본문 텍스트 (실패 시 빈 문자열)
    """
    browser = await get_browser()
    if not browser:
        return ""
    
    try:
        page = await browser.new_page()
        await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        
        # 페이지 HTML 가져오기
        html = await page.content()
        await page.close()
        
        # BeautifulSoup으로 본문 추출
        soup = BeautifulSoup(html, 'html.parser')
        
        # 불필요한 태그 제거
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'iframe']):
            tag.decompose()
        
        # 본문 영역 찾기 (우선순위 순)
        content = None
        selectors = [
            'article',
            '[role="main"]',
            '.article-body',
            '.article-content',
            '.post-content',
            '.entry-content',
            '.news-content',
            '.story-body',
            'main',
            '#content',
            '.content',
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text(separator=' ', strip=True)
                break
        
        # 본문 영역을 못 찾으면 body 전체에서 추출
        if not content:
            body = soup.find('body')
            if body:
                content = body.get_text(separator=' ', strip=True)
        
        if content:
            # 공백 정리 및 길이 제한
            content = ' '.join(content.split())
            return content[:max_chars]
        
        return ""
        
    except Exception as e:
        logger.warning(f"기사 본문 추출 실패 ({url[:50]}...): {e}")
        return ""


async def extract_multiple_articles(urls: list[str], max_chars: int = 300) -> dict[str, str]:
    """
    여러 기사 본문 동시 추출
    
    Args:
        urls: URL 리스트
        max_chars: 각 기사당 최대 문자 수
    
    Returns:
        {url: content} 딕셔너리
    """
    results = {}
    
    # 동시에 5개씩 처리
    batch_size = 5
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i + batch_size]
        tasks = [extract_article_content(url, max_chars) for url in batch]
        contents = await asyncio.gather(*tasks)
        
        for url, content in zip(batch, contents):
            results[url] = content
    
    logger.info(f"{len(urls)}개 기사 중 {sum(1 for v in results.values() if v)}개 본문 추출 성공")
    return results


async def close_browser():
    """브라우저 종료"""
    global _playwright, _browser
    
    if _browser:
        await _browser.close()
        _browser = None
    
    if _playwright:
        await _playwright.stop()
        _playwright = None
    
    logger.info("Playwright 브라우저 종료")
