"""Discord 알림 및 봇 모듈"""
import asyncio
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
import httpx

from src.utils.config import DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL
from src.utils.logger import get_logger
from src.analysis.llm_analyzer import TradeDecision

logger = get_logger(__name__)


# ==================== 웹훅 알림 (발송 전용) ====================

def send_webhook_message(content: str, embeds: list = None):
    """Discord 웹훅으로 메시지 발송"""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord 웹훅 URL이 설정되지 않음")
        return
    
    payload = {"content": content}
    if embeds:
        payload["embeds"] = embeds
    
    try:
        with httpx.Client() as client:
            res = client.post(DISCORD_WEBHOOK_URL, json=payload)
            res.raise_for_status()
        logger.info("Discord 웹훅 발송 완료")
    except Exception as e:
        logger.error(f"Discord 웹훅 발송 실패: {e}")


def notify_system_start():
    """시스템 시작 알림"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_webhook_message(f"🔔 **투자봇 시작** ({now})\n시장 분석을 시작합니다.")


def notify_trade_executed(decision: TradeDecision, success: bool, 
                          order_result: dict = None):
    """
    거래 실행 결과 알림 (판단 이유 포함)
    
    Args:
        decision: 매매 결정 정보
        success: 주문 성공 여부
        order_result: 주문 결과 (선택)
    """
    if decision.action == "buy":
        emoji = "📈"
        action_text = "매수"
        color = 0x00FF00  # 녹색
    else:
        emoji = "📉"
        action_text = "매도"
        color = 0xFF0000  # 빨간색
    
    status = "✅ 체결" if success else "❌ 실패"
    
    embed = {
        "title": f"{emoji} {action_text} {status}",
        "color": color if success else 0x808080,
        "fields": [
            {"name": "종목", "value": f"{decision.stock_name} ({decision.stock_code})", "inline": True},
            {"name": "수량", "value": f"{decision.quantity:,}주", "inline": True},
            {"name": "가격", "value": f"{decision.price:,}원" if decision.price > 0 else "시장가", "inline": True},
            {"name": "🧠 판단 이유", "value": decision.reason, "inline": False},
            {"name": "확신도", "value": f"{'⭐' * decision.confidence}{'☆' * (10 - decision.confidence)} ({decision.confidence}/10)", "inline": False},
        ],
        "timestamp": datetime.now().isoformat(),
    }
    
    send_webhook_message("", embeds=[embed])


def notify_daily_report(portfolio: list, total_value: int, 
                        daily_profit: int, daily_profit_rate: float):
    """일일 성과 리포트"""
    now = datetime.now().strftime("%Y-%m-%d")
    profit_emoji = "📈" if daily_profit >= 0 else "📉"
    profit_color = 0x00FF00 if daily_profit >= 0 else 0xFF0000
    
    # 보유 종목 요약
    holdings = ""
    for item in portfolio[:5]:  # 최대 5개만 표시
        holdings += f"• {item['name']}: {item['profit_rate']:+.2f}%\n"
    
    if len(portfolio) > 5:
        holdings += f"... 외 {len(portfolio) - 5}개 종목\n"
    
    embed = {
        "title": f"📊 일일 리포트 ({now})",
        "color": profit_color,
        "fields": [
            {"name": "총 평가금액", "value": f"{total_value:,}원", "inline": True},
            {"name": f"{profit_emoji} 일일 손익", "value": f"{daily_profit:+,}원 ({daily_profit_rate:+.2f}%)", "inline": True},
            {"name": "보유 종목", "value": holdings or "없음", "inline": False},
        ],
        "timestamp": datetime.now().isoformat(),
    }
    
    send_webhook_message("", embeds=[embed])


def notify_error(error_msg: str):
    """에러 알림"""
    send_webhook_message(f"⚠️ **에러 발생**\n```{error_msg}```")


def notify_news_summary(news_list: list, market_data: dict = None):
    """
    뉴스 및 시장 요약 알림
    
    Args:
        news_list: 뉴스 리스트
        market_data: 시장 데이터 (선택)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 뉴스 요약 (최대 5개)
    news_text = ""
    for i, news in enumerate(news_list[:5], 1):
        title = news.get("title", "")[:60]
        source = news.get("source", "").replace("google_", "")
        news_text += f"{i}. {title}...\n"
    
    if not news_text:
        news_text = "수집된 뉴스 없음"
    
    # 시장 요약
    market_text = ""
    if market_data and market_data.get("stocks"):
        gainers = market_data.get("top_gainers", [])[:3]
        losers = market_data.get("top_losers", [])[:3]
        
        if gainers:
            market_text += "📈 **상승**: "
            market_text += ", ".join([f"{s['name']}({s['change_rate']:+.1f}%)" for s in gainers])
            market_text += "\n"
        
        if losers:
            market_text += "📉 **하락**: "
            market_text += ", ".join([f"{s['name']}({s['change_rate']:+.1f}%)" for s in losers])
    
    embed = {
        "title": f"📰 시장 브리핑 ({now})",
        "color": 0x3498DB,  # 파란색
        "fields": [
            {"name": "📌 주요 뉴스", "value": news_text, "inline": False},
        ],
        "timestamp": datetime.now().isoformat(),
    }
    
    if market_text:
        embed["fields"].append({"name": "📊 관심종목 현황", "value": market_text, "inline": False})
    
    if market_data:
        filter_info = market_data.get("filter", "")
        if filter_info:
            embed["footer"] = {"text": f"필터: {filter_info}"}
    
    send_webhook_message("", embeds=[embed])


# ==================== Discord 봇 (양방향) ====================

class TradingBot(commands.Bot):
    """투자봇 Discord 봇"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)  # 기본 커맨드는 !로
    
    async def setup_hook(self):
        """봇 시작 시 명령어 등록"""
        
        @self.command(name="status")
        async def status(ctx):
            """현재 봇 상태 조회"""
            from src.trading import get_kis_client
            
            try:
                client = get_kis_client()
                await ctx.send("🤖 **봇 상태**: 정상 운영 중\n📊 시장 모니터링 중...")
            except Exception as e:
                await ctx.send(f"❌ 상태 조회 실패: {e}")
        
        @self.command(name="portfolio")
        async def portfolio(ctx):
            """포트폴리오 조회"""
            from src.trading import get_kis_client
            
            try:
                client = get_kis_client()
                balance = client.get_balance()
                
                output1 = balance.get("output1", [])
                output2 = balance.get("output2", [{}])[0]
                
                total = int(output2.get("tot_evlu_amt", 0))
                cash = int(output2.get("dnca_tot_amt", 0))
                
                msg = f"📊 **포트폴리오**\n"
                msg += f"💰 총 평가금액: {total:,}원\n"
                msg += f"💵 예수금: {cash:,}원\n\n"
                
                if output1:
                    msg += "📈 **보유 종목:**\n"
                    for item in output1[:5]:
                        name = item.get("prdt_name", "")
                        qty = item.get("hldg_qty", "0")
                        profit = float(item.get("evlu_pfls_rt", 0))
                        msg += f"• {name}: {qty}주 ({profit:+.2f}%)\n"
                else:
                    msg += "📭 보유 종목 없음"
                
                await ctx.send(msg)
            except Exception as e:
                await ctx.send(f"❌ 포트폴리오 조회 실패: {e}")
        
        @self.command(name="analyze")
        async def analyze(ctx, *, query: str = None):
            """종목 분석 요청 (한국/미국 주식 지원)"""
            if not query:
                await ctx.send("❓ 사용법:\n• `/analyze 삼성전자` (종목명)\n• `/analyze 005930` (한국 종목코드)\n• `/analyze TSLA` (미국 티커)")
                return
            
            await ctx.send(f"🔍 **{query}** 검색 및 분석 중... (잠시만 기다려주세요)")
            
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            from src.analysis import analyze_stock
            from src.trading import get_kis_client
            from src.data.stock_search import search_stock
            
            def do_analysis():
                """동기 분석 함수 (스레드에서 실행)"""
                # 1. 종목 검색
                stock_info = search_stock(query)
                
                if not stock_info:
                    return None, None, f"'{query}'에 해당하는 종목을 찾을 수 없습니다."
                
                code = stock_info["code"]
                market = stock_info["market"]
                name = stock_info.get("name", code)
                
                client = get_kis_client()
                
                # 2. 시세 조회 (시장별 분기)
                if market == "KR":
                    # 한국 주식
                    price_data = client.get_price(code)
                    current_price = int(price_data["output"]["stck_prpr"])
                    stock_name = price_data["output"].get("prdt_abrv_name", name)
                    market_label = "🇰🇷"
                else:
                    # 미국 주식
                    exchange = stock_info.get("exchange", "NAS")
                    price_data = client.get_overseas_price(exchange, code)
                    current_price = float(price_data["output"]["last"])
                    stock_name = price_data["output"].get("name", name)
                    market_label = "🇺🇸"
                
                # 3. LLM 분석
                result = analyze_stock(code, stock_name, current_price)
                
                return f"{market_label} {stock_name}", code, result
            
            try:
                # 스레드풀에서 실행 (Discord 하트비트 차단 방지)
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as pool:
                    stock_name, code, result = await loop.run_in_executor(pool, do_analysis)
                
                if stock_name is None:
                    await ctx.send(f"❌ {result}")
                    return
                
                # 메시지가 너무 길면 자르기
                if len(result) > 1800:
                    result = result[:1800] + "..."
                
                await ctx.send(f"📊 **{stock_name} ({code}) 분석 결과**\n{result}")
            except Exception as e:
                await ctx.send(f"❌ 분석 실패: {e}\n📌 종목명 또는 티커를 확인해주세요.")
        
        @self.command(name="stop")
        async def stop(ctx):
            """오늘 거래 중지"""
            await ctx.send("🛑 **거래 중지** - 오늘 추가 거래를 중단합니다.")
        
        @self.command(name="resume")
        async def resume(ctx):
            """거래 재개"""
            await ctx.send("▶️ **거래 재개** - 거래를 재개합니다.")
        
        @self.command(name="news")
        async def news(ctx):
            """최신 뉴스 조회"""
            from src.data import fetch_news
            
            try:
                news_list = fetch_news(max_items=5)
                msg = "📰 **최신 뉴스**\n\n"
                for i, n in enumerate(news_list, 1):
                    title = n.get("title", "")[:50]
                    msg += f"{i}. {title}...\n"
                await ctx.send(msg)
            except Exception as e:
                await ctx.send(f"❌ 뉴스 조회 실패: {e}")
    
    async def on_ready(self):
        logger.info(f"Discord 봇 로그인: {self.user}")
        
        # 슬래시 명령어 등록
        try:
            # 슬래시 명령어 정의
            @self.tree.command(name="status", description="봇 상태 확인")
            async def slash_status(interaction: discord.Interaction):
                await interaction.response.send_message("🤖 **봇 상태**: 정상 운영 중\n📊 시장 모니터링 중...")
            
            @self.tree.command(name="portfolio", description="포트폴리오 조회")
            async def slash_portfolio(interaction: discord.Interaction):
                await interaction.response.defer()
                from src.trading import get_kis_client
                try:
                    client = get_kis_client()
                    balance = client.get_balance()
                    output2 = balance.get("output2", [{}])[0]
                    total = int(output2.get("tot_evlu_amt", 0))
                    cash = int(output2.get("dnca_tot_amt", 0))
                    msg = f"📊 **포트폴리오**\n💰 총 평가금액: {total:,}원\n💵 예수금: {cash:,}원"
                    await interaction.followup.send(msg)
                except Exception as e:
                    await interaction.followup.send(f"❌ 조회 실패: {e}")
            
            @self.tree.command(name="analyze", description="종목 분석 (예: 삼성전자, TSLA)")
            @discord.app_commands.describe(query="종목명 또는 티커 (예: 삼성전자, 005930, TSLA)")
            async def slash_analyze(interaction: discord.Interaction, query: str):
                await interaction.response.defer()
                
                import asyncio
                from concurrent.futures import ThreadPoolExecutor
                from src.analysis import analyze_stock
                from src.trading import get_kis_client
                from src.data.stock_search import search_stock
                
                def do_analysis():
                    stock_info = search_stock(query)
                    if not stock_info:
                        return None, None, f"'{query}'에 해당하는 종목을 찾을 수 없습니다."
                    
                    code = stock_info["code"]
                    market = stock_info["market"]
                    name = stock_info.get("name", code)
                    client = get_kis_client()
                    
                    if market == "KR":
                        price_data = client.get_price(code)
                        current_price = int(price_data["output"]["stck_prpr"])
                        stock_name = price_data["output"].get("prdt_abrv_name", name)
                        label = "🇰🇷"
                    else:
                        exchange = stock_info.get("exchange", "NAS")
                        price_data = client.get_overseas_price(exchange, code)
                        current_price = float(price_data["output"]["last"])
                        stock_name = name
                        label = "🇺🇸"
                    
                    result = analyze_stock(code, stock_name, current_price)
                    return f"{label} {stock_name}", code, result
                
                try:
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor() as pool:
                        stock_name, code, result = await loop.run_in_executor(pool, do_analysis)
                    
                    if stock_name is None:
                        await interaction.followup.send(f"❌ {result}")
                        return
                    
                    if len(result) > 1800:
                        result = result[:1800] + "..."
                    await interaction.followup.send(f"📊 **{stock_name} ({code})**\n{result}")
                except Exception as e:
                    await interaction.followup.send(f"❌ 분석 실패: {e}")
            
            @self.tree.command(name="news", description="최신 뉴스 조회")
            async def slash_news(interaction: discord.Interaction):
                await interaction.response.defer()
                from src.data import fetch_news
                try:
                    news_list = fetch_news(max_items=5)
                    msg = "📰 **최신 뉴스**\n\n"
                    for i, n in enumerate(news_list, 1):
                        title = n.get("title", "")[:50]
                        msg += f"{i}. {title}...\n"
                    await interaction.followup.send(msg)
                except Exception as e:
                    await interaction.followup.send(f"❌ 뉴스 조회 실패: {e}")
            
            @self.tree.command(name="stop", description="오늘 거래 중지")
            async def slash_stop(interaction: discord.Interaction):
                await interaction.response.send_message("🛑 **거래 중지** - 오늘 추가 거래를 중단합니다.")
            
            @self.tree.command(name="resume", description="거래 재개")
            async def slash_resume(interaction: discord.Interaction):
                await interaction.response.send_message("▶️ **거래 재개** - 거래를 재개합니다.")
            
            # 글로벌 명령어 동기화
            synced = await self.tree.sync()
            logger.info(f"슬래시 명령어 {len(synced)}개 동기화 완료")
        except Exception as e:
            logger.error(f"슬래시 명령어 동기화 실패: {e}")


def run_discord_bot():
    """Discord 봇 실행 (별도 스레드에서 실행)"""
    if not DISCORD_BOT_TOKEN:
        logger.warning("Discord 봇 토큰이 설정되지 않음")
        return
    
    bot = TradingBot()
    
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Discord 봇 실행 실패: {e}")
