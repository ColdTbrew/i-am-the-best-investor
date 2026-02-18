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
        super().__init__(command_prefix="!", intents=intents)  # 기본 커맨드는 !로

        # 대화 기록 저장소 {user_id: {'last_time': datetime, 'messages': []}}
        self.conversations = {}
        state.discord_bot = self
    
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
            if mode.value == "paper":
                state.set_mode("paper")
                await interaction.response.send_message("🔄 모드 변경 완료: **PAPER** (모의투자)")
            elif mode.value == "real":
                from src.utils.config import REAL_ACCOUNTS
                if not REAL_ACCOUNTS:
                    await interaction.response.send_message("❌ 등록된 실전 계좌가 없습니다. `.env` 파일을 확인해주세요.")
                    return
                
                if len(REAL_ACCOUNTS) == 1:
                    # 계좌가 1개면 바로 선택
                    acc = REAL_ACCOUNTS[0]
                    state.set_mode("real")
                    state.set_real_account(acc["account_number"])
                    masked = acc["account_number"][-4:]
                    await interaction.response.send_message(
                        f"🔄 모드 변경 완료: **REAL** (실전투자)\n"
                        f"📋 계좌: ****{masked} ({acc['id']})"
                    )
                else:
                    # 계좌 선택 UI
                    view = AccountSelectView(REAL_ACCOUNTS)
                    msg = "🏦 **실전 계좌를 선택해주세요:**\n"
                    for acc in REAL_ACCOUNTS:
                        masked = acc["account_number"][-4:]
                        msg += f"• `{acc['id']}` — 계좌번호: ****{masked}\n"
                    await interaction.response.send_message(msg, view=view)

        # 수동 루틴 실행
        @self.tree.command(name="morning", description="🌅 아침 루틴 즉시 실행 (한국장 분석)")
        async def slash_morning(interaction: discord.Interaction):
            await interaction.response.defer()
            from src.scheduler.routines import run_morning_routine
            try:
                await interaction.followup.send("🌅 **아침 루틴 시작**\n한국장 분석 및 매수 추천을 실행합니다...")
                await run_morning_routine(None, channel=interaction.channel)
                await interaction.followup.send("✅ 아침 루틴 완료!")
            except Exception as e:
                await interaction.followup.send(f"❌ 아침 루틴 실패: {e}")

        @self.tree.command(name="evening", description="🌙 저녁 루틴 즉시 실행 (미국장 분석)")
        async def slash_evening(interaction: discord.Interaction):
            await interaction.response.defer()
            from src.scheduler.routines import run_evening_routine
            try:
                await interaction.followup.send("🌙 **저녁 루틴 시작**\n미국장 분석 및 포트폴리오 리포트를 실행합니다...")
                await run_evening_routine(None, channel=interaction.channel)
                await interaction.followup.send("✅ 저녁 루틴 완료!")
            except Exception as e:
                await interaction.followup.send(f"❌ 저녁 루틴 실패: {e}")

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

                res = await asyncio.to_thread(client.buy_stock, code, quantity)

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
                
                res = await asyncio.to_thread(client.sell_stock, code, quantity)
                
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

        # 4. 분석
        @self.tree.command(name="analyze", description="종목 분석")
        @discord.app_commands.describe(query="종목명 또는 티커")
        async def slash_analyze(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            from src.analysis import analyze_stock
            from src.trading import get_kis_client
            from src.data.stock_search import search_stock
            
            try:
                stock_info = search_stock(query)
                if not stock_info:
                    await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                    return

                code = stock_info["code"]
                name = stock_info.get("name", code)
                market = stock_info.get("market", "KR")

                client = get_kis_client()
                price = 0

                if market == "KR":
                    res = await asyncio.to_thread(client.get_price, code)
                    if res and 'output' in res:
                        price = float(res['output'].get('stck_prpr', 0))
                else:
                    # US
                    exchange = stock_info.get("exchange", "NAS")
                    res = await asyncio.to_thread(client.get_overseas_price, exchange, code)
                    if res and 'output' in res:
                        price = float(res['output'].get('last', 0))

                analysis = await asyncio.to_thread(analyze_stock, code, name, price)
                await interaction.followup.send(f"📊 **{name} ({code})**\n{analysis}")
            except Exception as e:
                 await interaction.followup.send(f"❌ 분석 중 에러 발생: {e}")

        @self.tree.command(name="chat", description="AI 투자 비서와 대화하기")
        @discord.app_commands.describe(query="질문할 내용")
        async def slash_chat(interaction: discord.Interaction, query: str):
            await interaction.response.defer()

            import asyncio
            from datetime import datetime, timedelta
            from concurrent.futures import ThreadPoolExecutor
            from src.analysis.llm_analyzer import chat_with_llm

            user_id = interaction.user.id
            now = datetime.now()

            # 대화 기록 관리 (5분 세션)
            history = []
            if user_id in self.conversations:
                session = self.conversations[user_id]
                if now - session['last_time'] < timedelta(minutes=5):
                    history = session['messages']
                    # 너무 길어지면 앞부분 자르기 (최근 10턴 유지)
                    if len(history) > 20:
                        history = history[-20:]
                else:
                    # 5분 지났으면 초기화
                    history = []

            try:
                # 스레드풀에서 실행 (Discord 하트비트 차단 방지)
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as pool:
                    response = await loop.run_in_executor(pool, chat_with_llm, query, history)

                # 대화 기록 업데이트
                history.append({"role": "user", "content": query})
                history.append({"role": "assistant", "content": response})
                self.conversations[user_id] = {
                    'last_time': now,
                    'messages': history
                }

                # 메시지가 너무 길면 나눠서 보내기 (Discord 제한 2000자)
                # 첫 번째 메시지는 질문을 포함하므로 길이를 계산해야 함
                header_format = "🗨️ **질문**: {}\n\n🤖 **답변**:\n"
                # 질문이 너무 길면 자름 (최대 200자)
                display_query = query[:200] + "..." if len(query) > 200 else query
                header = header_format.format(display_query)

                # 첫 번째 청크가 들어갈 수 있는 공간 계산
                # 2000 (Discord 제한) - header 길이 - 여유분(10)
                first_chunk_size = 2000 - len(header) - 10
                if first_chunk_size < 100: # 공간이 너무 부족하면 질문 표시 생략하거나 별도 메시지로 처리해야 하지만 여기선 질문을 더 줄임
                    display_query = display_query[:50] + "..."
                    header = header_format.format(display_query)
                    first_chunk_size = 2000 - len(header) - 10

                # 첫 번째 청크
                first_chunk = response[:first_chunk_size]
                remaining_response = response[first_chunk_size:]

                await interaction.followup.send(header + first_chunk)

                # 나머지 부분 전송 (1900자씩 끊어서)
                if remaining_response:
                    for i in range(0, len(remaining_response), 1900):
                        await interaction.followup.send(remaining_response[i:i+1900])

            except Exception as e:
                await interaction.followup.send(f"❌ 대화 실패: {e}")

        @self.tree.command(name="recommend", description="오늘의 추천 종목 3개")
        async def slash_recommend(interaction: discord.Interaction):
            await interaction.response.defer()

            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            from src.data import fetch_news, get_market_data, generate_stock_chart
            from src.analysis import get_daily_recommendations

            def get_recommendations_with_prediction():
                """동기 함수 - 추천 종목 조회 및 예측 차트 생성"""
                from src.analysis.price_predictor import predictor
                from src.trading import get_kis_client
                from pykrx import stock as pykrx_stock
                
                market_data = get_market_data()
                news_data = fetch_news(max_items=10)
                recommendations = get_daily_recommendations(market_data, news_data)
                
                client = get_kis_client()
                charts = []
                
                for rec in recommendations:
                    try:
                        # 1. 1개월치 과거 데이터 수집 (30일 + 여유)
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=45)
                        
                        prices = []
                        if len(rec.stock_code) == 6 and rec.stock_code.isdigit():
                            # 한국 주식
                            df = pykrx_stock.get_market_ohlcv(
                                start_date.strftime("%Y%m%d"),
                                end_date.strftime("%Y%m%d"),
                                rec.stock_code
                            )
                            if not df.empty:
                                prices = df['종가'].tail(30).to_list()
                        else:
                            # 미국 주식
                            from src.data.stock_search import search_stock
                            stock_info = search_stock(rec.stock_code)
                            exchange = stock_info.get("exchange", "NASD") if stock_info else "NASD"
                            
                            res = client.get_overseas_ohlcv(exchange, rec.stock_code, 
                                                         start_date.strftime("%Y%m%d"), 
                                                         end_date.strftime("%Y%m%d"))
                            output = res.get("output2", [])
                            if output:
                                # KIS 해외 일봉은 역순일 수 있음 확인 필요 (보통 최신이 앞)
                                prices = [float(x['clos']) for x in reversed(output[:30])]
                        
                        # 2. 예측 수행
                        prediction = None
                        if len(prices) >= 10:
                            prediction = predictor.predict_3day_trend(prices)
                        
                        # 3. 차트 생성 (예측 포함)
                        chart_path = generate_stock_chart(rec.stock_code, rec.stock_name, 
                                                        days=30, prediction_data=prediction)
                        charts.append(chart_path)
                    except Exception as e:
                        logger.error(f"{rec.stock_name} 예측/차트 생성 실패: {e}")
                        charts.append(None)
                
                return recommendations, charts

            try:
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as pool:
                    recommendations, charts = await loop.run_in_executor(pool, get_recommendations_with_prediction)

                if not recommendations:
                    await interaction.followup.send("❌ 추천 종목을 찾을 수 없습니다.")
                    return
                
                # 각 종목별 메시지 + 버튼 전송
                for i, rec in enumerate(recommendations):
                    # 가격 정보
                    emoji = "📈" if rec.change > 0 else "📉" if rec.change < 0 else "➖"
                    color = "🔴" if rec.change > 0 else "🔵" if rec.change < 0 else "⚪"
                    
                    price_str = f"**{rec.current_price:,}원**" if len(rec.stock_code) == 6 else f"**${rec.current_price:,.2f}**"
                    change_str = f"{rec.change:+,}원" if len(rec.stock_code) == 6 else ""

                    msg = f"**#{i+1} {rec.stock_name} ({rec.stock_code})**\n"
                    msg += f"💰 현재가: {price_str}\n"
                    msg += f"{emoji} 전일대비: {color} {change_str} ({rec.change_rate:+.2f}%)\n"
                    msg += f"⭐ 확신도: {'⭐' * rec.confidence}{'☆' * (10 - rec.confidence)}\n\n"
                    msg += f"📝 **추천 이유:**\n{rec.reason}\n\n"
                    msg += f"🔮 **AI 가격 예측 (향후 3일)**:\n"
                    msg += f"└ 🚀 Bull Case (상위 10%): 높은 확률로 추가 상승 가능성\n"
                    msg += f"└ 📉 Bear Case (하위 10%): 시장 변동 시 하락 지지선\n"
                    
                    # 매수 버튼 View 생성
                    view = BuyButtonView(rec.stock_code, rec.stock_name, rec.current_price)
                    
                    # 차트 이미지가 있으면 첨부
                    chart_path = charts[i] if i < len(charts) else None
                    if chart_path:
                        file = discord.File(chart_path, filename=f"{rec.stock_code}_chart.png")
                        await interaction.followup.send(msg, file=file, view=view)
                    else:
                        await interaction.followup.send(msg, view=view)

            except Exception as e:
                logger.error(f"추천 종목 조회 실패: {e}")
                await interaction.followup.send(f"❌ 추천 종목 조회 실패: {e}")

        @self.tree.command(name="recommend-by-model", description="AI 모델 예측 기반 기대 수익률 상위 종목 추천")
        async def slash_recommend_by_model(interaction: discord.Interaction):
            await interaction.response.defer()

            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            from src.data.stock_screener import KOSPI_WATCHLIST
            from src.analysis.price_predictor import predictor
            from src.data import generate_stock_chart
            from pykrx import stock as pykrx_stock
            from datetime import datetime, timedelta

            def analyze_candidates():
                """동기 함수 - 모든 후보 종목 예측 후 수익률 상위 추출"""
                candidates = KOSPI_WATCHLIST # 후보군 (코스피 우량주 16종)
                results = []

                end_date = datetime.now()
                start_date = end_date - timedelta(days=45)

                for stock in candidates:
                    try:
                        # 1. 데이터 수집
                        df = pykrx_stock.get_market_ohlcv(
                            start_date.strftime("%Y%m%d"),
                            end_date.strftime("%Y%m%d"),
                            stock["code"]
                        )
                        if df.empty: continue
                        
                        prices = df['종가'].tail(30).to_list()
                        current_price = prices[-1]

                        # 2. 예측
                        prediction = None
                        expected_return = -999.0
                        
                        if len(prices) >= 10:
                            prediction = predictor.predict_3day_trend(prices)
                            if prediction:
                                # 기대 수익률: (3일 뒤 중간값 - 현재가) / 현재가
                                target_price = prediction['median'][-1]
                                expected_return = (target_price - current_price) / current_price * 100

                        results.append({
                            "code": stock["code"],
                            "name": stock["name"],
                            "current_price": current_price,
                            "expected_return": expected_return,
                            "prediction": prediction,
                            "change": int(df['종가'].iloc[-1] - df['종가'].iloc[-2]) if len(df) > 1 else 0,
                            "change_rate": float((df['종가'].iloc[-1] - df['종가'].iloc[-2]) / df['종가'].iloc[-2] * 100) if len(df) > 1 else 0.0
                        })
                    except Exception as e:
                        logger.warning(f"{stock['name']} 분석 건너뜀: {e}")

                # 3. 수익률 순 정렬 후 상위 3개
                top_3 = sorted(results, key=lambda x: x['expected_return'], reverse=True)[:3]
                
                # 4. 상위 3개에 대한 차트 생성
                charts = []
                for item in top_3:
                    chart_path = generate_stock_chart(item["code"], item["name"], 
                                                   days=30, prediction_data=item["prediction"])
                    charts.append(chart_path)
                
                return top_3, charts

            try:
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as pool:
                    top_3, charts = await loop.run_in_executor(pool, analyze_candidates)

                if not top_3:
                    await interaction.followup.send("❌ 분석 가능한 추천 종목이 없습니다.")
                    return

                await interaction.followup.send(f"📊 **AI 모델(Chronos-Small) 기반 기대 수익률 상위 종목**\n(후보군: 코스피 우량주 {len(KOSPI_WATCHLIST)}종)\n{'-'*30}")

                for i, item in enumerate(top_3):
                    emoji = "📈" if item["change"] > 0 else "📉" if item["change"] < 0 else "➖"
                    color = "🔴" if item["change"] > 0 else "🔵" if item["change"] < 0 else "⚪"
                    
                    msg = f"**#{i+1} {item['name']} ({item['code']})**\n"
                    msg += f"💰 현재가: **{item['current_price']:,}원**\n"
                    msg += f"{emoji} 전일대비: {color} {item['change']:+,}원 ({item['change_rate']:+.2f}%)\n"
                    msg += f"🚀 **3일 뒤 예상 수익률: {item['expected_return']:+.2f}%**\n\n"
                    
                    view = BuyButtonView(item["code"], item["name"], item["current_price"])
                    
                    chart_path = charts[i]
                    if chart_path:
                        file = discord.File(chart_path, filename=f"{item['code']}_pred.png")
                        await interaction.followup.send(msg, file=file, view=view)
                    else:
                        await interaction.followup.send(msg, view=view)

            except Exception as e:
                logger.error(f"모델 추천 실패: {e}")
                await interaction.followup.send(f"❌ 모델 추천 중 에러 발생: {e}")

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

        # 5. 관심종목 (Favorites)
        fav_group = discord.app_commands.Group(name="fav", description="관심종목 관리")

        @fav_group.command(name="list", description="관심종목 시세 조회")
        async def fav_list(interaction: discord.Interaction):
            await interaction.response.defer()
            from src.utils.favorites import favorites_manager
            from src.trading import get_kis_client
            import asyncio

            user_id = interaction.user.id
            favs = favorites_manager.get_favorites(user_id)

            if not favs:
                await interaction.followup.send("📭 관심종목이 없습니다. `/fav add`로 추가해보세요.")
                return

            client = get_kis_client()

            # Helper to fetch single price synchronously
            def get_price_sync(item):
                code = item["code"]
                market = item["market"]
                name = item["name"]
                try:
                    price = 0
                    change = 0
                    change_rate = 0

                    if market == "KR":
                        res = client.get_price(code)
                        if res and 'output' in res:
                            price = float(res['output']['stck_prpr'])
                            change = float(res['output']['prdy_vrss'])
                            change_rate = float(res['output']['prdy_ctrt'])
                    else:
                        exchange = item.get("exchange", "NAS")
                        res = client.get_overseas_price(exchange, code)
                        if res and 'output' in res:
                            price = float(res['output']['last'])
                            change = float(res['output']['diff'])
                            change_rate = float(res['output']['rate'])

                    return {
                        "name": name,
                        "code": code,
                        "price": price,
                        "change": change,
                        "change_rate": change_rate,
                        "market": market
                    }
                except Exception as e:
                    return {"name": name, "code": code, "error": str(e)}

            # Run in parallel
            loop = asyncio.get_running_loop()
            futures = [loop.run_in_executor(None, get_price_sync, item) for item in favs]
            results = await asyncio.gather(*futures)

            msg = "⭐ **관심종목 시세**\n"
            for res in results:
                if "error" in res:
                    msg += f"• **{res['name']}** ({res['code']}): ❌ 조회 실패\n"
                    continue

                emoji = "🔴" if res['change'] > 0 else "🔵" if res['change'] < 0 else "⚪"
                price_fmt = f"{res['price']:,.0f}원" if res['market'] == "KR" else f"${res['price']:,.2f}"
                change_fmt = f"{res['change']:+,.0f}" if res['market'] == "KR" else f"{res['change']:+,.2f}"

                msg += f"• **{res['name']}** ({res['code']}) {emoji}\n"
                msg += f"  └ {price_fmt} ({change_fmt}, {res['change_rate']:+.2f}%)\n"

            await interaction.followup.send(msg)

        @fav_group.command(name="add", description="관심종목 추가")
        @discord.app_commands.describe(query="종목명 또는 코드")
        async def fav_add(interaction: discord.Interaction, query: str):
            await interaction.response.defer(ephemeral=True)
            from src.utils.favorites import favorites_manager
            from src.data.stock_search import search_stock

            stock_info = await asyncio.to_thread(search_stock, query)
            if not stock_info:
                await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                return

            user_id = interaction.user.id
            if await favorites_manager.add_favorite(user_id, stock_info):
                name = stock_info.get("name", stock_info["code"])
                await interaction.followup.send(f"✅ **{name}** 관심종목 추가 완료!")
            else:
                await interaction.followup.send(f"⚠️ 이미 관심종목에 있습니다.")

        @fav_group.command(name="remove", description="관심종목 제거")
        @discord.app_commands.describe(query="종목명 또는 코드")
        async def fav_remove(interaction: discord.Interaction, query: str):
            await interaction.response.defer(ephemeral=True)
            from src.utils.favorites import favorites_manager
            from src.data.stock_search import search_stock

            stock_info = await asyncio.to_thread(search_stock, query)
            if not stock_info:
                await interaction.followup.send(f"❌ '{query}' 종목을 찾을 수 없습니다.")
                return

            code = stock_info["code"]
            name = stock_info.get("name", code)
            user_id = interaction.user.id

            if await favorites_manager.remove_favorite(user_id, code):
                await interaction.followup.send(f"🗑️ **{name}** 관심종목 삭제 완료!")
            else:
                await interaction.followup.send(f"⚠️ 관심종목에 없는 종목입니다.")

        self.tree.add_command(fav_group)

        synced = await self.tree.sync()
        logger.info(f"슬래시 명령어 {len(synced)}개 동기화 완료")

    async def _send_portfolio(self, interaction: discord.Interaction, followup: bool = False):
        """포트폴리오 메시지 전송 공통 함수"""
        from src.trading import get_kis_client
        
        try:
            mode = state.get_mode()
            client = get_kis_client(mode)
            balance = await asyncio.to_thread(client.get_balance)

            output1 = balance.get("output1", [])
            output2 = balance.get("output2", [{}])[0]
            
            total_eval = int(output2.get("tot_evlu_amt", 0))
            cash = int(output2.get("dnca_tot_amt", 0))
            
            stock_eval_total = sum(int(item.get("evlu_amt", 0)) for item in output1)
            
            # 총 평가 손익 계산
            total_pnl = int(output2.get("evlu_pfls_smtl_amt", 0))  # 평가손익합계금액
            total_pnl_rate = float(output2.get("evlu_pfls_rt", 0)) if output2.get("evlu_pfls_rt") else 0  # 평가손익률

            pnl_emoji = "📈" if total_pnl >= 0 else "📉"

            msg = f"� **포트폴리오 ({mode.upper()})**\n"
            msg += f"💰 총 평가금액: {total_eval:,}원\n"
            msg += f"💵 예수금: {cash:,}원\n"
            msg += f"📦 주식 평가금액: {stock_eval_total:,}원\n"
            msg += f"{pnl_emoji} **총 평가손익**: {total_pnl:+,}원 ({total_pnl_rate:+.2f}%)\n\n"
            
            if output1:
                msg += "📈 **보유 종목**:\n"
                for item in output1[:10]:
                    name = item.get("prdt_name", "")
                    qty = int(item.get("hldg_qty", 0))
                    profit_rate = float(item.get("evlu_pfls_rt", 0))
                    profit_amt = int(item.get("evlu_pfls_amt", 0))  # 평가손익금액
                    current = int(item.get("prpr", 0))
                    buy_price = float(item.get("pchs_avg_pric", 0))
                    eval_amt = int(item.get("evlu_amt", 0))

                    emoji = "🔴" if profit_rate > 0 else "🔵" if profit_rate < 0 else "⚪"
                    msg += f"• **{name}** ({qty}주) {emoji}\n"
                    msg += f"  └ 매수가: {buy_price:,.0f}원 | 현재가: {current:,}원\n"
                    msg += f"  └ 평가금액: {eval_amt:,}원 | **손익: {profit_amt:+,}원** ({profit_rate:+.2f}%)\n"
            else:
                msg += "📭 보유 종목 없음"
            
            if followup:
                # 이미 defer된 상태거나 추가 메시지로 보낼 때
                await interaction.followup.send(msg)
            else:
                await interaction.followup.send(msg)
        except Exception as e:
            logger.error(f"포트폴리오 조회 실패: {e}")
            await interaction.followup.send(f"❌ 포트폴리오 조회 중 에러 발생: {e}")


class AccountSelectView(discord.ui.View):
    """실전 계좌 선택 View"""
    def __init__(self, accounts: list):
        super().__init__(timeout=60)
        self.accounts = accounts
        
        # 드롭다운 메뉴 생성
        options = []
        for acc in accounts:
            masked = acc["account_number"][-4:]
            options.append(discord.SelectOption(
                label=f"{acc['id']} — ****{masked}",
                value=acc["account_number"],
                description=f"계좌번호: ****{masked}"
            ))
        
        select = discord.ui.Select(
            placeholder="계좌를 선택하세요...",
            options=options,
            custom_id="account_select"
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: discord.Interaction):
        selected_number = interaction.data["values"][0]
        state.set_mode("real")
        state.set_real_account(selected_number)
        masked = selected_number[-4:]
        
        # 선택된 계좌의 ID 찾기
        acc_id = "unknown"
        for acc in self.accounts:
            if acc["account_number"] == selected_number:
                acc_id = acc["id"]
                break
        
        await interaction.response.edit_message(
            content=f"✅ 모드 변경 완료: **REAL** (실전투자)\n📋 계좌: ****{masked} ({acc_id})",
            view=None
        )


class BuyButtonView(discord.ui.View):
    """추천 종목 매수 버튼 View"""
    def __init__(self, stock_code: str, stock_name: str, price: float):
        super().__init__(timeout=None)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.price = price

    @discord.ui.button(label="1주 즉시 매수", style=discord.ButtonStyle.green, custom_id="buy_now_btn")
    async def buy_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        """즉시 매수 버튼 클릭 시 실행"""
        from src.trading import get_kis_client
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            mode = state.get_mode()
            client = get_kis_client(mode)
            
            # 시장가 매수
            res = await asyncio.to_thread(client.buy_stock, self.stock_code, 1)
            
            if res.get("rt_cd") == "0":
                await interaction.followup.send(
                    f"✅ **매수 완료 ({mode.upper()})**\n종목: {self.stock_name} ({self.stock_code})\n수량: 1주\n주문번호: {res.get('output', {}).get('ODNO')}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ 매수 실패: {res.get('msg1')}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}", ephemeral=True)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary, custom_id="cancel_btn")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("취소되었습니다.", ephemeral=True)


class SellButtonView(discord.ui.View):
    """추천 종목 매도 버튼 View"""
    def __init__(self, stock_code: str, stock_name: str, quantity: int):
        super().__init__(timeout=None)
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.quantity = quantity

    @discord.ui.button(label="전량 즉시 매도", style=discord.ButtonStyle.red, custom_id="sell_now_btn")
    async def sell_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        """즉시 매도 버튼 클릭 시 실행"""
        from src.trading import get_kis_client
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            mode = state.get_mode()
            client = get_kis_client(mode)
            
            # 전량 매도
            res = await asyncio.to_thread(client.sell_stock, self.stock_code, self.quantity)
            
            if res.get("rt_cd") == "0":
                await interaction.followup.send(
                    f"✅ **매도 완료 ({mode.upper()})**\n종목: {self.stock_name} ({self.stock_code})\n수량: {self.quantity}주\n주문번호: {res.get('output', {}).get('ODNO')}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ 매도 실패: {res.get('msg1')}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}", ephemeral=True)


class MomentumApprovalView(discord.ui.View):
    """급등주 단타 매수 승인 View (2분 타임아웃)"""

    def __init__(self, code: str, name: str, qty: int, price: int, rate: float):
        super().__init__(timeout=120)
        self.code = code
        self.name = name
        self.qty = qty
        self.price = price
        self.rate = rate
        self._responded = False

    @discord.ui.button(label="✅ 매수 승인", style=discord.ButtonStyle.green, custom_id="momentum_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._responded:
            await interaction.response.send_message("이미 처리된 요청입니다.", ephemeral=True)
            return
        self._responded = True
        self.stop()

        await interaction.response.defer()

        from src.trading.momentum import execute_momentum_buy
        res = await asyncio.to_thread(execute_momentum_buy, self.code, self.name, self.qty, self.price)

        if res.get("rt_cd") == "0":
            embed = discord.Embed(
                title=f"✅ 단타 매수 체결",
                description=f"**{self.name}** ({self.code})",
                color=0x00CC44,
                timestamp=datetime.now(),
            )
            embed.add_field(name="수량", value=f"{self.qty}주", inline=True)
            embed.add_field(name="현재가", value=f"{self.price:,}원", inline=True)
            embed.add_field(name="등락률", value=f"{self.rate:+.1f}%", inline=True)
            embed.add_field(name="예상 금액", value=f"{self.price * self.qty:,}원", inline=True)
            embed.add_field(name="승인자", value=interaction.user.display_name, inline=True)
        else:
            err = res.get("msg1", "알 수 없는 오류")
            embed = discord.Embed(
                title=f"❌ 단타 매수 실패",
                description=f"**{self.name}** ({self.code})\n사유: {err}",
                color=0xFF4444,
                timestamp=datetime.now(),
            )

        await interaction.edit_original_response(embed=embed, view=None)

    @discord.ui.button(label="❌ 거절", style=discord.ButtonStyle.secondary, custom_id="momentum_reject_btn")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._responded:
            await interaction.response.send_message("이미 처리된 요청입니다.", ephemeral=True)
            return
        self._responded = True
        self.stop()

        embed = discord.Embed(
            title="🚫 단타 매수 거절됨",
            description=f"**{self.name}** ({self.code}) — {interaction.user.display_name}님이 거절했습니다.",
            color=0x888888,
            timestamp=datetime.now(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        """2분 내 응답 없으면 자동 만료"""
        logger.info(f"단타 승인 타임아웃: {self.name} ({self.code})")
        # 채널 메시지를 직접 수정할 수 없으므로 웹훅으로 알림
        send_webhook_message(
            f"⏰ **단타 매수 승인 시간 초과** — {self.name} ({self.code}) {self.qty}주 요청이 만료되었습니다."
        )


async def send_momentum_approval(code: str, name: str, qty: int, price: int, rate: float):
    """급등주 단타 매수 승인 요청 메시지를 디스코드 채널로 전송"""
    if not state.discord_bot:
        logger.warning("Discord 봇이 초기화되지 않아 승인 요청을 보낼 수 없습니다.")
        send_webhook_message(
            f"⚠️ 디스코드 봇 미초기화 — 단타 승인 불가\n{name} ({code}) {qty}주 @ {price:,}원"
        )
        return False

    try:
        bot = state.discord_bot
        target_channel = None

        for guild in bot.guilds:
            for cand in guild.text_channels:
                perms = cand.permissions_for(guild.me)
                if perms.send_messages and perms.embed_links:
                    target_channel = cand
                    break
            if target_channel:
                break

        if not target_channel:
            logger.error("단타 승인 메시지를 보낼 채널을 찾지 못했습니다.")
            send_webhook_message(
                f"⚠️ 채널 없음 — 단타 승인 불가\n{name} ({code}) {qty}주 @ {price:,}원"
            )
            return False

        embed = discord.Embed(
            title=f"🚀 급등주 단타 매수 승인 요청",
            description=f"**{name}** ({code})",
            color=0xFFAA00,
            timestamp=datetime.now(),
        )
        embed.add_field(name="현재가", value=f"{price:,}원", inline=True)
        embed.add_field(name="등락률", value=f"{rate:+.1f}%", inline=True)
        embed.add_field(name="매수 수량", value=f"{qty}주", inline=True)
        embed.add_field(name="예상 금액", value=f"{price * qty:,}원", inline=True)
        embed.set_footer(text="2분 내에 승인하지 않으면 자동 만료됩니다.")

        view = MomentumApprovalView(code, name, qty, price, rate)
        await target_channel.send(embed=embed, view=view)
        logger.info(f"단타 승인 요청 전송 완료: {name} ({code}) → #{target_channel.name}")
        return True

    except Exception as e:
        logger.error(f"단타 승인 요청 전송 실패: {e}")
        send_webhook_message(f"❌ 단타 승인 요청 전송 실패: {e}")
        return False


async def send_recommendations_with_buttons(recommendations, market="KR", channel=None):
    """스케줄러/루틴에서 버튼이 포함된 추천 메시지 전송"""
    if not state.discord_bot:
        logger.warning("Discord 봇이 초기화되지 않아 메시지를 보낼 수 없습니다.")
        return False
        
    try:
        bot = state.discord_bot
        target_channel = channel
        
        if not target_channel:
            logger.info(f"채널 탐색 시작 (봇이 참여 중인 서버 수: {len(bot.guilds)})")
            for guild in bot.guilds:
                # 보낼 수 있는 채널 후보들
                candidates = []
                if guild.system_channel:
                    candidates.append(guild.system_channel)
                
                for c in guild.text_channels:
                    candidates.append(c)
                
                # 권한 재검증 및 최종 선택
                for cand in candidates:
                    perms = cand.permissions_for(guild.me)
                    if perms.send_messages and perms.embed_links:
                        target_channel = cand
                        logger.info(f"메시지 전송 채널 선택됨: [{guild.name}] #{cand.name}")
                        break
                
                if target_channel: break
            
        if not target_channel:
            logger.error("메시지를 보낼 수 있는 채널을 찾지 못했습니다. (권한 부족 또는 서버 없음)")
            return False

        # 채널 정보 및 권한 로깅
        perms = target_channel.permissions_for(target_channel.guild.me)
        logger.info(f"[{market}] 메시지 전송 시도: #{target_channel.name} (ID: {target_channel.id})")
        logger.info(f"[{market}] 권한 상태 - send_messages: {perms.send_messages}, embed_links: {perms.embed_links}")

        await target_channel.send(f"🌅 **오늘의 {market} 추천 종목 (봇 직접 알림)**")
        
        for rec in recommendations:
            emoji = "📈" if rec.change > 0 else "📉" if rec.change < 0 else "➖"
            color = 0x00FF00 if rec.change >= 0 else 0xFF0000
            
            embed = discord.Embed(
                title=f"{rec.stock_name} ({rec.stock_code})",
                description=rec.reason,
                color=color,
                timestamp=datetime.now()
            )
            embed.add_field(name="현재가", value=f"{rec.current_price:,.0f}원" if market=="KR" else f"${rec.current_price:,.2f}", inline=True)
            embed.add_field(name="확신도", value="⭐" * rec.confidence, inline=True)
            
            view = BuyButtonView(rec.stock_code, rec.stock_name, rec.current_price)
            await target_channel.send(embed=embed, view=view)
            
        return True
    except Exception as e:
        logger.error(f"봇 추천 메시지 전송 실패: {e}")
        # 웹훅으로 폴백
        try:
            embeds = []
            for rec in recommendations:
                embeds.append({
                    "title": f"🌅 오늘의 추천 ({market}): {rec.stock_name}",
                    "description": rec.reason,
                    "fields": [
                        {"name": "코드", "value": rec.stock_code, "inline": True},
                        {"name": "현재가", "value": f"{rec.current_price:,.0f}원" if market=="KR" else f"${rec.current_price:,.2f}", "inline": True},
                        {"name": "확신도", "value": f"{rec.confidence}/10", "inline": True},
                    ],
                    "color": 0x00FF00 if rec.change >= 0 else 0xFF0000
                })
            send_webhook_message(f"🌅 **오늘의 {market} 추천 종목**", embeds=embeds)
            logger.info("웹훅으로 폴백 전송 완료")
        except Exception as we:
            logger.error(f"웹훅 폴백도 실패: {we}")
        return False


async def send_sell_recommendations_with_buttons(candidates, market="KR", channel=None):
    """매도 추천 알림 (버튼 포함)"""
    if not state.discord_bot or not candidates:
        return False
        
    try:
        bot = state.discord_bot
        target_channel = channel
        
        if not target_channel:
            for guild in bot.guilds:
                for cand in guild.text_channels:
                    perms = cand.permissions_for(guild.me)
                    if perms.send_messages and perms.embed_links:
                        target_channel = cand
                        break
                if target_channel: break
            
        if not target_channel:
            logger.error("매도 추천을 보낼 채널을 찾지 못했습니다.")
            return False

        await target_channel.send(f"📉 **보유 종목 매도 추천 ({market})**")
        
        for item in candidates:
            name = item.get("prdt_name", item.get("ovrs_pdno", "알수없음"))
            code = item.get("pdno", item.get("ovrs_pdno", ""))
            qty = int(item.get("hldg_qty", item.get("ord_psbl_qty", 0)))
            profit = float(item.get("evlu_pfls_rt", 0))
            
            embed = discord.Embed(
                title=f"{name} ({code})",
                description=f"현재 수익률: **{profit:+.2f}%**\n보유 수량: {qty}주",
                color=0xFF0000,
                timestamp=datetime.now()
            )
            
            view = SellButtonView(code, name, qty)
            await target_channel.send(embed=embed, view=view)
            
        return True
    except Exception as e:
        logger.error(f"매도 추천 메시지 전송 실패: {e}")
        # 웹훅으로 폴백
        try:
            embeds = []
            for item in candidates:
                name = item.get("prdt_name", item.get("ovrs_pdno", "알수없음"))
                code = item.get("pdno", item.get("ovrs_pdno", ""))
                profit = float(item.get("evlu_pfls_rt", 0))
                embeds.append({
                    "title": f"📉 매도 추천 ({market}): {name}",
                    "description": f"수익률: {profit:+.2f}%",
                    "color": 0xFF0000
                })
            send_webhook_message(f"📉 **오늘의 {market} 매도 추천**", embeds=embeds)
            logger.info("매도 추천 웹훅 폴백 전송 완료")
        except Exception as we:
            logger.error(f"매도 웹훅 폴백도 실패: {we}")
        return False


def run_discord_bot():
    if not DISCORD_BOT_TOKEN:
        logger.warning("Discord 봇 토큰 없음")
        return
    bot = TradingBot()
    bot.run(DISCORD_BOT_TOKEN)
