"""Discord 알림 및 봇 모듈"""
import asyncio
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
import httpx

from src.utils.config import DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL
from src.utils.logger import get_logger
from src.utils.state import state
from src.analysis.llm_analyzer import TradeDecision

logger = get_logger(__name__)


# ==================== 웹훅 알림 (발송 전용) ====================

def send_webhook_message(content: str, embeds: list = None):
    """Discord 웹훅으로 메시지 발송"""
    if not DISCORD_WEBHOOK_URL:
        # logger.warning("Discord 웹훅 URL이 설정되지 않음")
        return
    
    payload = {"content": content}
    if embeds:
        payload["embeds"] = embeds
    
    try:
        with httpx.Client() as client:
            res = client.post(DISCORD_WEBHOOK_URL, json=payload)
            res.raise_for_status()
    except Exception as e:
        logger.error(f"Discord 웹훅 발송 실패: {e}")


def notify_system_start():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = state.get_mode()
    send_webhook_message(f"🔔 **투자봇 시작** ({now})\n모드: {mode.upper()}\n시장 분석을 시작합니다.")


def notify_trade_executed(decision: TradeDecision, success: bool, order_result: dict = None):
    if decision.action == "buy":
        emoji = "📈"
        action_text = "매수"
        color = 0x00FF00
    else:
        emoji = "📉"
        action_text = "매도"
        color = 0xFF0000
    
    status = "✅ 체결" if success else "❌ 실패"
    
    embed = {
        "title": f"{emoji} {action_text} {status}",
        "color": color if success else 0x808080,
        "fields": [
            {"name": "종목", "value": f"{decision.stock_name} ({decision.stock_code})", "inline": True},
            {"name": "수량", "value": f"{decision.quantity:,}주", "inline": True},
            {"name": "가격", "value": f"{decision.price:,}원" if decision.price > 0 else "시장가", "inline": True},
            {"name": "🧠 판단 이유", "value": decision.reason, "inline": False},
            {"name": "계좌 모드", "value": state.get_mode().upper(), "inline": False},
        ],
        "timestamp": datetime.now().isoformat(),
    }
    send_webhook_message("", embeds=[embed])


def notify_daily_report(portfolio: list, total_value: int, daily_profit: int, daily_profit_rate: float):
    now = datetime.now().strftime("%Y-%m-%d")
    profit_emoji = "📈" if daily_profit >= 0 else "📉"
    profit_color = 0x00FF00 if daily_profit >= 0 else 0xFF0000
    
    holdings = ""
    for item in portfolio[:5]:
        holdings += f"• {item['name']}: {item['profit_rate']:+.2f}%\n"
    if len(portfolio) > 5:
        holdings += f"... 외 {len(portfolio) - 5}개 종목\n"
    
    embed = {
        "title": f"📊 일일 리포트 ({now})",
        "description": f"모드: {state.get_mode().upper()}",
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
    send_webhook_message(f"⚠️ **에러 발생**\n```{error_msg}```")


def notify_news_summary(news_list: list, market_data: dict = None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    news_text = ""
    for i, news in enumerate(news_list[:5], 1):
        title = news.get("title", "")[:60]
        news_text += f"{i}. {title}...\n"
    
    embed = {
        "title": f"📰 시장 브리핑 ({now})",
        "color": 0x3498DB,
        "fields": [{"name": "📌 주요 뉴스", "value": news_text or "없음", "inline": False}],
        "timestamp": datetime.now().isoformat(),
    }
    send_webhook_message("", embeds=[embed])


# ==================== Discord 봇 (양방향) ====================

class TradingBot(commands.Bot):
    """투자봇 Discord 봇"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    
    async def setup_hook(self):
        """봇 시작 시 명령어 등록"""
        
        # 1. 봇 상태 및 모드 설정
        @self.tree.command(name="status", description="봇 상태 및 현재 모드 확인")
        async def slash_status(interaction: discord.Interaction):
            mode = state.get_mode()
            await interaction.response.send_message(f"🤖 **봇 상태**: 정상 운영 중\n⚙️ **현재 모드**: {mode.upper()}")

        @self.tree.command(name="mode", description="거래 계좌 모드 변경 (Real / Paper)")
        @discord.app_commands.describe(mode="변경할 모드 (real 또는 paper)")
        @discord.app_commands.choices(mode=[
            discord.app_commands.Choice(name="실전투자 (Real)", value="real"),
            discord.app_commands.Choice(name="모의투자 (Paper)", value="paper"),
        ])
        async def slash_mode(interaction: discord.Interaction, mode: discord.app_commands.Choice[str]):
            current = state.get_mode()
            if current == mode.value:
                await interaction.response.send_message(f"이미 **{mode.value.upper()}** 모드입니다.")
            else:
                state.set_mode(mode.value)
                await interaction.response.send_message(f"🔄 모드 변경 완료: **{mode.value.upper()}**")

        # 2. 포트폴리오
        @self.tree.command(name="portfolio", description="포트폴리오 조회")
        async def slash_portfolio(interaction: discord.Interaction):
            await interaction.response.defer()
            await self._send_portfolio(interaction)

        # 3. 매수/매도
        @self.tree.command(name="buy", description="주식 매수 (시장가)")
        @discord.app_commands.describe(query="종목명 또는 코드", quantity="매수 수량")
        async def slash_buy(interaction: discord.Interaction, query: str, quantity: int):
            if quantity <= 0:
                await interaction.response.send_message("❌ 수량은 1주 이상이어야 합니다.")
                return
            await interaction.response.defer()

            from src.trading import get_kis_client
            from src.data.stock_search import search_stock

            try:
                stock_info = search_stock(query)
                if not stock_info:
                    await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                    return

                # 현재는 한국 주식만 (API 제약 등 고려)
                if stock_info["market"] != "KR":
                    await interaction.followup.send("❌ 자동 매매는 현재 한국 주식만 지원합니다.")
                    return

                code = stock_info["code"]
                name = stock_info.get("name", code)

                mode = state.get_mode()
                client = get_kis_client(mode)

                res = client.buy_stock(code, quantity)

                if res.get("rt_cd") == "0":
                    msg = f"📈 **매수 주문 전송 ({mode.upper()})**\n"
                    msg += f"종목: {name} ({code})\n"
                    msg += f"수량: {quantity}주\n"
                    msg += f"주문번호: {res.get('output', {}).get('ODNO', '알수없음')}"
                    await interaction.followup.send(msg)

                    # 자동 포트폴리오 업데이트 (잠시 대기 후 실행)
                    await asyncio.sleep(1)
                    await self._send_portfolio(interaction, followup=True)
                else:
                    await interaction.followup.send(f"❌ 매수 실패: {res.get('msg1')}")

            except Exception as e:
                await interaction.followup.send(f"❌ 매수 중 에러: {e}")

        @self.tree.command(name="sell", description="주식 매도 (시장가)")
        @discord.app_commands.describe(query="종목명 또는 코드", quantity="매도 수량")
        async def slash_sell(interaction: discord.Interaction, query: str, quantity: int):
            if quantity <= 0:
                await interaction.response.send_message("❌ 수량은 1주 이상이어야 합니다.")
                return
            await interaction.response.defer()

            from src.trading import get_kis_client
            from src.data.stock_search import search_stock

            try:
                stock_info = search_stock(query)
                if not stock_info:
                    await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                    return

                if stock_info["market"] != "KR":
                    await interaction.followup.send("❌ 자동 매매는 현재 한국 주식만 지원합니다.")
                    return
                
                code = stock_info["code"]
                name = stock_info.get("name", code)
                
                mode = state.get_mode()
                client = get_kis_client(mode)
                
                res = client.sell_stock(code, quantity)
                
                if res.get("rt_cd") == "0":
                    msg = f"📉 **매도 주문 전송 ({mode.upper()})**\n"
                    msg += f"종목: {name} ({code})\n"
                    msg += f"수량: {quantity}주\n"
                    msg += f"주문번호: {res.get('output', {}).get('ODNO', '알수없음')}"
                    await interaction.followup.send(msg)
                    
                    # 자동 포트폴리오 업데이트
                    await asyncio.sleep(1)
                    await self._send_portfolio(interaction, followup=True)
                else:
                    await interaction.followup.send(f"❌ 매도 실패: {res.get('msg1')}")
                    
            except Exception as e:
                await interaction.followup.send(f"❌ 매도 중 에러: {e}")

        # 4. 분석, 뉴스 등 기타 명령어 유지
        @self.tree.command(name="analyze", description="종목 분석")
        @discord.app_commands.describe(query="종목명 또는 티커")
        async def slash_analyze(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            # (기존 로직 단순화 호출)
            from src.analysis import analyze_stock
            from src.trading import get_kis_client
            from src.data.stock_search import search_stock
            
            stock_info = search_stock(query)
            if not stock_info:
                await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                return
            
            code = stock_info["code"]
            name = stock_info.get("name", code)
            
            # 가격 조회
            client = get_kis_client(state.get_mode())
            price = 0
            try:
                if stock_info["market"] == "KR":
                    res = client.get_price(code)
                    price = float(res["output"]["stck_prpr"])
                else:
                    res = client.get_overseas_price(stock_info.get("exchange", "NAS"), code)
                    price = float(res["output"]["last"])
            except:
                pass
            
            analysis = analyze_stock(code, name, price)
            await interaction.followup.send(f"📊 **{name} ({code})**\n{analysis}")

        @self.tree.command(name="news", description="최신 뉴스 조회")
        async def slash_news(interaction: discord.Interaction):
            await interaction.response.defer()
            from src.data import fetch_news
            try:
                news_list = fetch_news(max_items=5)
                msg = "📰 **최신 뉴스**\n\n"
                for i, n in enumerate(news_list, 1):
                    msg += f"{i}. {n.get('title', '')[:50]}...\n"
                await interaction.followup.send(msg)
            except:
                await interaction.followup.send("❌ 뉴스 조회 실패")

        synced = await self.tree.sync()
        logger.info(f"슬래시 명령어 {len(synced)}개 동기화 완료")

    async def _send_portfolio(self, interaction: discord.Interaction, followup: bool = False):
        """포트폴리오 메시지 전송 공통 함수"""
        from src.trading import get_kis_client
        
        try:
            mode = state.get_mode()
            client = get_kis_client(mode)
            balance = client.get_balance()

            output1 = balance.get("output1", [])
            output2 = balance.get("output2", [{}])[0]
            
            total_eval = int(output2.get("tot_evlu_amt", 0))
            cash = int(output2.get("dnca_tot_amt", 0))
            
            msg = f"📊 **포트폴리오 ({mode.upper()})**\n"
            msg += f"💰 총 평가금액: {total_eval:,}원\n"
            msg += f"💵 예수금: {cash:,}원\n\n"
            
            if output1:
                msg += "📈 **보유 종목**:\n"
                for item in output1[:10]:
                    name = item.get("prdt_name", "")
                    qty = int(item.get("hldg_qty", 0))
                    profit = float(item.get("evlu_pfls_rt", 0))
                    current = int(item.get("prpr", 0))

                    emoji = "🔴" if profit > 0 else "🔵" if profit < 0 else "⚪"
                    msg += f"• {name}: {qty}주 @ {current:,}원 {emoji} ({profit:+.2f}%)\n"
            else:
                msg += "📭 보유 종목 없음"
            
            if followup:
                # 이미 defer된 상태거나 추가 메시지로 보낼 때
                await interaction.followup.send(msg)
            else:
                await interaction.followup.send(msg)

        except Exception as e:
            err_msg = f"❌ 포트폴리오 조회 실패: {e}"
            if followup:
                await interaction.followup.send(err_msg)
            else:
                await interaction.followup.send(err_msg)


def run_discord_bot():
    if not DISCORD_BOT_TOKEN:
        logger.warning("Discord 봇 토큰 없음")
        return
    bot = TradingBot()
    bot.run(DISCORD_BOT_TOKEN)
