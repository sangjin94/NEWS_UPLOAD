import os
import sys
import json
import asyncio
import datetime
import glob
import urllib.request
import argparse
from typing import List, Dict, Any

# Windows 터미널 유니코드 인코딩 대응
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # 구버전 파이썬 대응
        pass

import yfinance as yf
import google.generativeai as genai
import edge_tts
from moviepy import ImageClip, AudioFileClip, CompositeVideoClip, TextClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# 시각화 라이브러리 (Rich)
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

# 스크립트 파일 위치를 기준으로 작업 디렉토리 변경
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# .env 파일 로드 (준비된 경우)
load_dotenv()

# 인코딩 문제 해결을 위한 콘솔 설정
console = Console(force_terminal=True, color_system="auto", soft_wrap=True)

class PokemonShortsPipeline:
    def __init__(self, market: str = 'US'):
        self.market = market.upper()
        # 시장별 워치리스트 정의
        if self.market == 'KR':
            self.watchlist = ['005930.KS', '000660.KS', '373220.KS', '207940.KS', '005380.KS', 
                              '005490.KS', '035420.KS', '035720.KS', '247540.KQ', '028300.KQ']
            self.currency_symbol = "₩"
            self.indices = ['^KS11', '^KQ11']
        else:
            self.watchlist = ['QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL', 'AMD', 'AVGO']
            self.currency_symbol = "$"
            self.indices = ['^IXIC', '^GSPC', '^SOX']
            
        self.output_dir = "media_assets"
        self.video_filename = f"final_shorts_{self.market}_{datetime.datetime.now().strftime('%H%M')}.mp4"
        self.resolution = (1080, 1920)
        self.tts_voice = "ko-KR-SunHiNeural"
        
        # API 설정
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            
        # API 설정
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def log_step(self, title: str):
        console.print(Panel(f"[bold cyan]{title}[/bold cyan]", expand=False))

    # --- STEP 1: Market Data & Script ---
    def fetch_market_data(self) -> Dict[str, Any]:
        """주식 데이터를 수집합니다."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[yellow]{self.market} 시장 데이터 수집 중...", total=len(self.watchlist) + len(self.indices))
            
            market_summary = []
            news_summary = []
            
            # 지수 및 주요 섹터 추가
            track_list = self.watchlist + self.indices
            
            for ticker_symbol in track_list:
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period="2d")
                    
                    if not hist.empty and len(hist) >= 1:
                        current_close = hist['Close'].iloc[-1]
                        prev_close = hist['Close'].iloc[0] if len(hist) >= 2 else current_close
                        volume = hist['Volume'].iloc[-1] if 'Volume' in hist else 0
                        pct_change = ((current_close - prev_close) / prev_close) * 100 if prev_close != 0 else 0
                        
                        # 종목만 요약에 추가 (지수는 제외하고 뉴스용으로만 사용 가능)
                        if ticker_symbol in self.watchlist:
                            market_summary.append({
                                "ticker": ticker_symbol,
                                "price": round(current_close, 2),
                                "change": round(pct_change, 2),
                                "volume": int(volume)
                            })
                    
                    # 뉴스 수집 (모든 종목/지수에서 수집)
                    recent_news = ticker.news
                    if recent_news and isinstance(recent_news, list):
                        for n in recent_news[:5]:
                            title = n.get('title') or n.get('summary', '')
                            if title:
                                news_summary.append(f"[{ticker_symbol}] {title}")
                except Exception as e:
                    console.print(f"[red]⚠️ {ticker_symbol} 실패: {e}[/red]")
                progress.update(task, advance=1)

        # 결과 테이블 출력
        table = Table(title=f"📈 {self.market} 주요 종목 실시간 시황")
        table.add_column("티커", style="cyan")
        table.add_column("현재가", justify="right")
        table.add_column("등락률(%)", justify="right")
        for s in sorted(market_summary, key=lambda x: abs(x['change']), reverse=True)[:5]:
            color = "green" if s['change'] >= 0 else "red"
            table.add_row(s['ticker'], f"{self.currency_symbol}{s['price']:,}", f"[{color}]{s['change']:+}%[/{color}]")
        console.print(table)

        return {
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "market": self.market,
            "top_stocks": sorted(market_summary, key=lambda x: x['volume'], reverse=True)[:5],
            "market_news": news_summary[:15]
        }

    def generate_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Gemini를 사용해 뉴스 스타일의 대본을 생성합니다."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다.")

        system_instruction = f"""
        너는 전문 주식 뉴스 아나운서이자 쇼츠 영상 기획자야.
        오늘의 {'한국 코스피/코스닥' if self.market == 'KR' else '미국 나스닥'} 시장 데이터를 바탕으로 쇼츠 대본을 작성해.
        
        [임무]
        1. 제공된 데이터 중 주제가 서로 다른 가장 중요한 뉴스 3개를 엄선해.
        2. 각 씬의 'narration'은 짧고 임팩트 있는 한 문장으로 작성해.
        3. 각 씬 데이터에 'related_stock'과 'stock_change' 필드를 추가해.
        4. 시각화 개선을 위해 'visual_cue'(예: 'bullish', 'bearish', 'neutral', 'warning')와 'headline' 필드를 추가해.
        5. 유튜브 알고리즘에 최적화된 제목, 설명, 그리고 20개 이상의 관련 태그(SEO 최적화)를 포함해.
        6. 대본 구성(6-8개): 오프닝, 이슈 1(2씬), 이슈 2(2씬), 이슈 3(2씬), 클로징.
        
        [JSON 구조]
        {{
          "title": "...",
          "scenes": [
            {{
              "scene_number": 1, 
              "narration": "...", 
              "related_stock": "...", 
              "stock_change": "...",
              "visual_cue": "...",
              "headline": "..."
            }},
            ...
          ],
          "youtube_metadata": {{
             "title": "...", 
             "description": "...", 
             "tags": ["#태그1", "#태그2", ...]
          }}
        }}
        """
        
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        user_prompt = f"현재 시간 {current_time}. 서로 다른 카테고리의 핫뉴스 3개를 선정해 시각적으로 강렬한 1분 쇼츠 대본을 만들어줘:\n{json.dumps(market_data, ensure_ascii=False)}"
        
        model = genai.GenerativeModel('gemini-flash-latest', system_instruction=system_instruction)
        generation_config = genai.GenerationConfig(response_mime_type="application/json", temperature=0.7)
        
        with console.status("[bold green]Gemini가 대본을 집필 중입니다..."):
            try:
                response = model.generate_content(user_prompt, generation_config=generation_config)
                data = json.loads(response.text)
                
                # 리스트로 반환된 경우 첫 번째 요소 추출
                if isinstance(data, list):
                    script_data = data[0]
                else:
                    script_data = data
                
                # 데이터 정규화 및 기본값 설정
                if "youtube_metadata" not in script_data:
                    script_data["youtube_metadata"] = {
                        "title": "오늘의 나스닥 포켓몬 배틀 브리핑 #Shorts",
                        "description": "자동 생성된 주식 브리핑입니다.",
                        "tags": ["#Shorts", "#주식"]
                    }
                
                # 씬 데이터 키 유연하게 처리 (scenes, script, shorts_script 등)
                possible_keys = ["scenes", "script", "shorts_script", "video_script"]
                for pk in possible_keys:
                    if pk in script_data and isinstance(script_data[pk], list):
                        script_data["scenes"] = script_data[pk]
                        break
                
                # 만약 scenes가 없고 나라레이션이 루트에 있는 경우 (단일 씬 응답 방어)
                if "scenes" not in script_data and "narration" in script_data:
                    single_scene = {
                        "scene_number": 1,
                        "narration": script_data.get("narration", ""),
                        "image_prompt": script_data.get("image_prompt", "A high-tech financial scene"),
                        "related_stock": script_data.get("related_stock", ""),
                        "stock_change": script_data.get("stock_change", "")
                    }
                    script_data["scenes"] = [single_scene]
                
                # 씬 데이터 정규화
                if "scenes" in script_data:
                    for i, scene in enumerate(script_data["scenes"]):
                        if "scene_number" not in scene:
                            scene["scene_number"] = i + 1
                        if "narration" not in scene:
                            scene["narration"] = scene.get("line", scene.get("text", "정보를 불러오는 중입니다."))
                
                title = script_data.get("youtube_metadata", {}).get("title", "No Title")
                console.print(f"[bold green]✅ 대본 생성 완료: {title}[/bold green]")
                
                # 디버깅을 위해 JSON 파일로 저장
                with open("script_data.json", "w", encoding="utf-8") as f:
                    json.dump(script_data, f, ensure_ascii=False, indent=2)
                
                return script_data
            except Exception as e:
                console.print(f"[red]❌ 응답 파싱 실패: {e}[/red]")
                raise e

    # --- STEP 2: Media Generation ---
    async def generate_assets(self, script_data: Dict[str, Any]):
        """오디오와 대시보드 이미지를 생성합니다."""
        scenes = script_data.get("scenes", [])
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            total_tasks = len(scenes) * 2
            task = progress.add_task("[magenta]미디어 자산 생성 중...", total=total_tasks)
            
            for scene in scenes:
                num = scene["scene_number"]
                narration = scene["narration"]
                
                # Audio (edge-tts)
                audio_path = os.path.join(self.output_dir, f"scene_{num}.mp3")
                communicate = edge_tts.Communicate(narration, self.tts_voice, rate="+20%")
                await communicate.save(audio_path)
                progress.update(task, advance=1, description=f"[magenta]씬 {num} 오디오 생성됨")
                
                # Dashboard Image (Pillow)
                image_path = os.path.join(self.output_dir, f"scene_{num}.png")
                self.draw_dashboard(scene, image_path)
                progress.update(task, advance=1, description=f"[magenta]씬 {num} 대시보드 이미지 완성")

    def draw_dashboard(self, scene: Dict[str, Any], output_path: str):
        """Pillow를 사용하여 전문적인 주식 뉴스 대시보드를 생성합니다."""
        narration = scene.get("narration", "")
        headline = scene.get("headline", "STOCK NEWS")
        ticker = scene.get("related_stock", "")
        change_val = str(scene.get("stock_change", "0"))
        cue = scene.get("visual_cue", "neutral").lower()

        # 1. 배경 설정
        bg_colors = {
            "bullish": (15, 30, 20),
            "bearish": (30, 15, 15),
            "warning": (35, 30, 10),
            "neutral": (20, 20, 25)
        }
        bg_color = bg_colors.get(cue, bg_colors["neutral"])
        img = Image.new('RGB', self.resolution, color=bg_color)
        draw = ImageDraw.Draw(img)

        # 2. 폰트 로드
        font_paths = [
            "C:\\Windows\\Fonts\\malgunbd.ttf", 
            "C:\\Windows\\Fonts\\malgun.ttf",
            "C:\\Windows\\Fonts\\gulim.ttc"
        ]
        font_path = next((fp for fp in font_paths if os.path.exists(fp)), None)
        
        def get_font(size):
            return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

        # 3. 디자인 요소: 배경 패턴
        for i in range(0, self.resolution[0], 100):
            draw.line([(i, 0), (i, self.resolution[1])], fill=(40, 40, 45), width=1)
        for i in range(0, self.resolution[1], 100):
            draw.line([(0, i), (self.resolution[0], i)], fill=(40, 40, 45), width=1)

        # 4. 상단 헤드라인 바
        bar_color = (180, 20, 20) if "bear" in cue else (20, 130, 40) if "bull" in cue else (40, 60, 180)
        draw.rectangle([0, 120, self.resolution[0], 280], fill=bar_color)
        
        # 헤드라인 폰트 조절 (가로 폭에 맞춰 축소)
        headline_size = 80
        h_font = get_font(headline_size)
        h_bbox = draw.textbbox((0, 0), headline, font=h_font)
        while (h_bbox[2] - h_bbox[0]) > (self.resolution[0] - 120) and headline_size > 40:
            headline_size -= 5
            h_font = get_font(headline_size)
            h_bbox = draw.textbbox((0, 0), headline, font=h_font)
        
        draw.text((60, 200 - (h_bbox[3]-h_bbox[1])/2), headline, font=h_font, fill=(255, 255, 255))
        draw.text((self.resolution[0] - 350, 180), f"{self.market} MARKET", font=get_font(40), fill=(255, 255, 255, 150))

        # 5. 중앙 메인 정보
        if ticker:
            draw.ellipse([340, 500, 740, 900], outline=bar_color, width=15)
            
            # 티커 폰트 조절
            ticker_size = 120
            t_font = get_font(ticker_size)
            t_bbox = draw.textbbox((0, 0), ticker, font=t_font)
            while (t_bbox[2] - t_bbox[0]) > (self.resolution[0] - 100) and ticker_size > 50:
                ticker_size -= 10
                t_font = get_font(ticker_size)
                t_bbox = draw.textbbox((0, 0), ticker, font=t_font)

            draw.text(((self.resolution[0] - (t_bbox[2]-t_bbox[0]))/2, 650), ticker, font=t_font, fill=(255, 255, 255))
            
            is_up = "+" in change_val or (not "-" in change_val and change_val != "0" and change_val != "0.00%")
            badge_color = (255, 40, 40) if is_up else (40, 80, 255)
            badge_text = change_val if "%" in change_val else f"{change_val}%"
            draw.rectangle([340, 950, 740, 1080], fill=badge_color, outline=(255, 255, 255), width=5)
            c_bbox = draw.textbbox((0, 0), badge_text, font=get_font(80))
            draw.text(((self.resolution[0] - (c_bbox[2]-c_bbox[0]))/2, 970), badge_text, font=get_font(80), fill=(255, 255, 255))

        # 6. 트렌드 라인 (랜덤 데코레이션)
        import random
        points = [(100 + i * 90, 1350 + random.randint(-60, 60)) for i in range(10)]
        draw.line(points, fill=bar_color, width=10, joint="curve")

        # 7. 하단 자막 영역
        draw.rectangle([0, self.resolution[1] - 450, self.resolution[0], self.resolution[1]], fill=(0, 0, 0, 180))
        
        margin = 80
        max_w = self.resolution[0] - (margin * 2)
        font_sub = get_font(55)
        words = narration.split()
        lines, current_line = [], ""
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            bbox = draw.textbbox((0, 0), test_line, font=font_sub)
            if (bbox[2] - bbox[0]) <= max_w: current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        
        y_text = self.resolution[1] - 380
        for line in lines[:3]:
            l_bbox = draw.textbbox((0, 0), line, font=font_sub)
            draw.text(((self.resolution[0] - (l_bbox[2]-l_bbox[0]))/2, y_text), line, font=font_sub, fill=(255, 220, 0))
            y_text += 85

        draw.text((self.resolution[0] - 380, self.resolution[1] - 80), "@STOCK_SHORTS_AI", font=get_font(30), fill=(120, 120, 120))
        img.save(output_path)

    # --- STEP 3: Video Synthesis ---
    def synthesize_video(self, script_data: Dict[str, Any]):
        """영상을 합성합니다."""
        console.print(f"[dim]🛠️ synthesize_video 시작. Keys: {list(script_data.keys())}[/dim]")
        scenes = script_data.get("scenes", [])
        console.print(f"[dim]🎞️ 씬 개수: {len(scenes)}[/dim]")
        clips = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]영상 클립 합성 중...", total=len(scenes))
            
            for scene in scenes:
                num = scene["scene_number"]
                audio_path = os.path.join(self.output_dir, f"scene_{num}.mp3")
                image_path = os.path.join(self.output_dir, f"scene_{num}.png")
                
                console.print(f"[dim]🔍 씬 {num} 확인 중: {audio_path}, {image_path}[/dim]")
                
                if not os.path.exists(audio_path) or not os.path.exists(image_path):
                    console.print(f"[yellow]⚠️ 씬 {num} 파일 누락[/yellow]")
                    continue
                    
                audio = AudioFileClip(audio_path)
                # 이미 자막이 합성된 이미지 클립 생성
                clip = ImageClip(image_path).with_duration(audio.duration).with_audio(audio)
                
                # 가끔 이미지 크기가 다를 수 있으므로 리사이즈 보장
                clip = clip.resized(height=self.resolution[1])
                clip = clip.cropped(x_center=clip.w/2, width=self.resolution[0])
                    
                clips.append(clip)
                progress.update(task, advance=1)
                
            if not clips:
                raise ValueError("합성할 영상 클립이 하나도 없습니다. STEP 2의 파일 생성을 확인하세요.")
                
            final_video = concatenate_videoclips(clips, method="compose")
            final_video.write_videofile(self.video_filename, fps=24, codec="libx264", audio_codec="aac", logger=None)
            
        console.print(f"[bold green]🎬 영상 렌더링 완료: {self.video_filename}[/bold green]")

    # --- STEP 4: YouTube Upload ---
    def upload_to_youtube(self, script_data: Dict[str, Any]):
        """유튜브에 업로드합니다."""
        if not os.path.exists("client_secret.json"):
            console.print("[red]❌ 'client_secret.json'이 없어 업로드를 생략합니다.[/red]")
            return

        console.print("[bold blue]🚀 유튜브 업로드 프로세스 시작...[/bold blue]")
        
        try:
            # OAuth 2.0 인증
            scopes = ["https://www.googleapis.com/auth/youtube.upload"]
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", scopes)
            
            # 인증 토큰 캐싱 (매번 브라우저를 열지 않도록)
            credentials_file = "token.json"
            if os.path.exists(credentials_file):
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                creds = Credentials.from_authorized_user_file(credentials_file, scopes)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            else:
                creds = flow.run_local_server(port=0, authorization_prompt_message="브라우저에서 유튜브 로그인을 완료해주세요.")
                with open(credentials_file, 'w') as token:
                    token.write(creds.to_json())

            youtube = build("youtube", "v3", credentials=creds)

            metadata = script_data.get("youtube_metadata", {})
            title = metadata.get("title", "오늘의 나스닥 포켓몬 배틀")
            description = metadata.get("description", "자동 생성된 주식 브리핑 쇼츠입니다.")
            tags = metadata.get("tags", ["#Shorts", "#주식", "#나스닥"])

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": tags,
                    "categoryId": "27"  # Education
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(self.video_filename, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

            with console.status("[bold blue]영상을 유튜브에 전송 중입니다..."):
                response = request.execute()

            console.print(f"[bold green]🎉 업로드 성공! 영상 ID: {response['id']}[/bold green]")
            console.print(f"🔗 링크: https://youtu.be/{response['id']}")

        except Exception as e:
            console.print(f"[red]❌ 유튜브 업로드 실패: {e}[/red]")

    async def run(self):
        try:
            console.print(Panel.fit(f"POKEMON STOCK SHORTS PIPELINE - {self.market}", title="🔥", border_style="bold yellow"))
            
            # (기존 logic 동일)
            self.log_step("STEP 1: 데이터 수집 및 기획")
            market_data = self.fetch_market_data()
            script_data = self.generate_script(market_data)
            
            # 2. 자산 생성
            self.log_step("STEP 2: 미디어 자산 생성")
            await self.generate_assets(script_data)
            
            # 3. 영상 합성
            self.log_step("STEP 3: 영상 합성 및 렌더링")
            self.synthesize_video(script_data)
            
            # 4. 업로드
            self.log_step("STEP 4: 유튜브 업로드")
            self.upload_to_youtube(script_data)
            
            console.print(f"\n[bold green]✨ {self.market} 파이프라인이 성공적으로 완료되었습니다! ✨[/bold green]")
            
        except Exception as e:
            console.print(f"\n[bold red]❌ 파이프라인 중단 오류 발생: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Shorts Pipeline")
    parser.add_argument("--market", type=str, default="US", choices=["US", "KR"], help="Market to process (US or KR)")
    args = parser.parse_args()
    
    pipeline = PokemonShortsPipeline(market=args.market)
    asyncio.run(pipeline.run())
