import os
import sys
import json
import asyncio
import datetime
import glob
import urllib.request
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
    def __init__(self):
        self.watchlist = ['QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL', 'AMD', 'AVGO']
        self.output_dir = "media_assets"
        self.video_filename = "final_shorts.mp4"
        self.resolution = (1080, 1920)
        self.tts_voice = "ko-KR-SunHiNeural"
        
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
            task = progress.add_task("[yellow]시장 데이터 수집 중...", total=len(self.watchlist))
            
            market_summary = []
            news_summary = []
            
            # 지수 및 주요 섹터 추가 (뉴스 다양성 확보)
            track_list = self.watchlist + ['^IXIC', '^GSPC', '^SOX', 'USO', 'GLD']
            
            for ticker_symbol in track_list:
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    # 데이터 수집 (티커 요약용)
                    if ticker_symbol in self.watchlist:
                        hist = ticker.history(period="2d")
                        if len(hist) >= 2:
                            prev_close = hist['Close'].iloc[0]
                            current_close = hist['Close'].iloc[1]
                            volume = hist['Volume'].iloc[1]
                            pct_change = ((current_close - prev_close) / prev_close) * 100
                            
                            market_summary.append({
                                "ticker": ticker_symbol,
                                "price": round(current_close, 2),
                                "change": round(pct_change, 2),
                                "volume": int(volume)
                            })
                    
                    # 뉴스 수집 (모든 종목/지수에서 수집하여 다양성 확보)
                    recent_news = ticker.news
                    if recent_news and isinstance(recent_news, list):
                        for n in recent_news[:3]:
                            title = n.get('title') or n.get('summary', '')
                            if title:
                                news_summary.append(f"[{ticker_symbol}] {title}")
                except Exception as e:
                    console.print(f"[red]⚠️ {ticker_symbol} 실패: {e}[/red]")
                progress.update(task, advance=1)

        # 결과 테이블 출력
        table = Table(title="📈 수집된 주요 종목 실시간 시황")
        table.add_column("티커", style="cyan")
        table.add_column("현재가", justify="right")
        table.add_column("등락률(%)", justify="right")
        for s in sorted(market_summary, key=lambda x: abs(x['change']), reverse=True)[:5]:
            color = "green" if s['change'] >= 0 else "red"
            table.add_row(s['ticker'], f"${s['price']}", f"[{color}]{s['change']}%[/{color}]")
        console.print(table)

        return {
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "top_stocks": sorted(market_summary, key=lambda x: x['volume'], reverse=True)[:5],
            "market_news": news_summary[:10]  # 상위 10개 뉴스 전달
        }

    def generate_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Gemini를 사용해 뉴스 스타일의 대본을 생성합니다."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다.")

        system_instruction = """
        너는 전문 주식 뉴스 아나운서이자 쇼츠 영상 기획자야.
        
        [임무]
        1. 제공된 데이터 중 주제가 **서로 다른(테크, 거시경제, 원자재/에너지 등)** 가장 중요한 뉴스 3개를 엄선해.
        2. 각 씬의 'narration'은 짧은 한 문장으로 작성하고, 반드시 **관련 종목 이름과 등락률(%)**을 포함해.
        3. 각 씬 데이터에 'related_stock'(예: NVDA)과 'stock_change'(예: +2.5) 필드를 추가해. (시각적 뱃지 생성용)
        4. 전체 대사는 한국어로 뉴스 전달 톤으로 작성해.
        5. 반드시 다음 JSON 구조를 지켜:
           {
             "title": "...",
             "scenes": [
               {"scene_number": 1, "narration": "...", "image_prompt": "...", "related_stock": "...", "stock_change": "..."},
               ...
             ],
             "youtube_metadata": {...}
           }
        6. 씬 구성(6-8개): 오프닝, 이슈 1(2씬), 이슈 2(2씬), 이슈 3(2씬), 클로징.
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
                
                # 씬 데이터 키 유연하게 처리 (scenes, script, shorts_script 등)
                if "scenes" in script_data:
                    for i, scene in enumerate(script_data["scenes"]):
                        if "scene_number" not in scene:
                            scene["scene_number"] = scene.get("scene", i + 1)
                        if "narration" not in scene:
                            scene["narration"] = scene.get("line", scene.get("text", ""))
                        if "image_prompt" not in scene:
                            # 별도의 image_prompts 리스트가 있는 경우와 action이 있는 경우 처리
                            prompts = script_data.get("image_prompts", [])
                            if i < len(prompts):
                                scene["image_prompt"] = prompts[i]
                            else:
                                scene["image_prompt"] = scene.get("action", "A cool monster scene")
                
                title = script_data["youtube_metadata"].get("title", "No Title")
                console.print(f"[bold green]✅ 대본 생성 완료: {title}[/bold green]")
                
                # 디버깅 및 이미지 생성 가이드를 위해 JSON 파일로 저장
                with open("script_data.json", "w", encoding="utf-8") as f:
                    json.dump(script_data, f, ensure_ascii=False, indent=2)
                
                return script_data
            except Exception as e:
                console.print(f"[red]❌ 응답 파싱 실패: {e}[/red]")
                console.print(f"Raw Response: {response.text}")
                raise e

    # --- STEP 2: Media Generation ---
    async def generate_assets(self, script_data: Dict[str, Any]):
        """오디오와 이미지를 생성합니다."""
        scenes = script_data.get("scenes", [])
        console.print(f"[dim]📁 현재 작업 디렉토리: {os.getcwd()}[/dim]")
        console.print(f"[dim]📂 미디어 저장 경로: {os.path.abspath(self.output_dir)}[/dim]")
        
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
                img_prompt = scene["image_prompt"]
                
                # Audio (edge-tts)
                audio_path = os.path.join(self.output_dir, f"scene_{num}.mp3")
                if not narration.strip():
                    narration = "데이터를 불러오는 중입니다."
                
                console.print(f"[dim]🎙️ 씬 {num} 나레이션 (속도+20%): {narration[:30]}...[/dim]")
                communicate = edge_tts.Communicate(narration, self.tts_voice, rate="+20%")
                await communicate.save(audio_path)
                
                # 파일 크기 확인 (0바이트 방지)
                if os.path.exists(audio_path) and os.path.getsize(audio_path) == 0:
                    console.print(f"[red]⚠️ 씬 {num} 오디오 생성 실패 (0바이트)[/red]")
                else:
                    progress.update(task, advance=1, description=f"[magenta]씬 {num} 오디오 생성됨")
                
                # Image (Pillow with Subtitles)
                image_path = os.path.join(self.output_dir, f"scene_{num}.png")
                
                # 이미지 생성 로직 (Pillow를 사용하여 자막 직접 합성)
                try:
                    # 배경 이미지 (기존 이미지가 없으면 검은 배경 생성, 있으면 로드)
                    if os.path.exists(image_path):
                        img = Image.open(image_path).convert('RGB')
                        # 1080x1920이 아니면 리사이즈
                        if img.size != self.resolution:
                            img = img.resize(self.resolution, Image.Resampling.LANCZOS)
                    else:
                        img = Image.new('RGB', self.resolution, color=(20, 20, 25))
                        
                    draw = ImageDraw.Draw(img)
                    
                    # 윈도우 한글 폰트 설정
                    font_paths = [
                        "C:\\Windows\\Fonts\\malgun.ttf", 
                        "C:\\Windows\\Fonts\\malgunbd.ttf", 
                        "C:\\Windows\\Fonts\\gulim.ttc"
                    ]
                    font = None
                    for fp in font_paths:
                        if os.path.exists(fp):
                            font = ImageFont.truetype(fp, 60)
                            font_bold = ImageFont.truetype(fp, 80)
                            break
                    
                    if not font:
                        font = ImageFont.load_default()
                        font_bold = font

                    # 자막 박스 (모바일 최적화: 2줄 제한 및 가로 여백 확보)
                    margin = 80
                    line_height = 90
                    max_chars = 18  # 모바일 가독성을 위해 한 줄당 글자 수 축소
                    
                    # 텍스트 줄바꿈
                    words = narration.split()
                    lines = []
                    current_line = ""
                    for word in words:
                        if len(current_line + word) <= max_chars:
                            current_line += (" " if current_line else "") + word
                        else:
                            lines.append(current_line)
                            current_line = word
                    lines.append(current_line)
                    
                    # 최대 2줄만 유지 (Gemini가 짧게 주겠지만 안전장치)
                    lines = lines[:2]
                    
                    # 자막 영역 높이 계산
                    rect_h = len(lines) * line_height + 100
                    draw.rectangle(
                        [0, self.resolution[1] - rect_h, self.resolution[0], self.resolution[1]],
                        fill=(0, 0, 0, 180)
                    )
                    
                    # 텍스트 그리기
                    y_start = self.resolution[1] - rect_h + 50
                    for i, line in enumerate(lines):
                        # 텍스트 너비 및 높이 계산을 위한 getbbox 사용
                        bbox = draw.textbbox((0, 0), line, font=font)
                        w = bbox[2] - bbox[0]
                        draw.text(((self.resolution[0] - w) / 2, y_start + i * line_height), line, font=font, fill=(255, 255, 255))
                    
                    # 상단 제목 추가
                    title_text = "MARKET BRIEFING"
                    bbox_t = draw.textbbox((0, 0), title_text, font=font_bold)
                    wt = bbox_t[2] - bbox_t[0]
                    draw.rectangle([0, 100, self.resolution[0], 250], fill=(200, 0, 0))
                    draw.text(((self.resolution[0] - wt) / 2, 130), title_text, font=font_bold, fill=(255, 255, 255))
                    
                    # 주가 뱃지 (V4 신규 기능: [종목] +% 강조)
                    ticker_name = scene.get("related_stock")
                    change_val = str(scene.get("stock_change", ""))
                    if ticker_name and change_val:
                        badge_text = f"[{ticker_name}] {change_val}%"
                        # 한국식 색상: 빨강=상승, 파랑=하락
                        is_up = "+" in change_val or (not "-" in change_val and change_val != "0")
                        badge_color = (255, 50, 50) if is_up else (50, 50, 255)
                        
                        bbox_b = draw.textbbox((0, 0), badge_text, font=font_bold)
                        wb = bbox_b[2] - bbox_b[0]
                        hb = bbox_b[3] - bbox_b[1]
                        
                        # 화면 중앙 우측에 배치
                        badge_x = self.resolution[0] - wb - 100
                        badge_y = 400
                        draw.rectangle([badge_x - 20, badge_y - 20, badge_x + wb + 20, badge_y + hb + 20], fill=badge_color)
                        draw.text((badge_x, badge_y), badge_text, font=font_bold, fill=(255, 255, 255))
                    
                    img.save(image_path)
                    progress.update(task, advance=1, description=f"[magenta]씬 {num} 자막 이미지 완성")
                except Exception as e:
                    console.print(f"[red]⚠️ 이미지 자막 합성 실패: {e}[/red]")
                    progress.update(task, advance=1)

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
            console.print(Panel.fit("POKEMON STOCK SHORTS PIPELINE", title="🔥", border_style="bold yellow"))
            
            # 1. 데이터 및 대본
            if os.path.exists("script_data.json"):
                console.print("[yellow]📦 기존 대본 데이터(script_data.json)를 발견했습니다. 재생성을 건너뜁니다.[/yellow]")
                with open("script_data.json", "r", encoding="utf-8") as f:
                    script_data = json.load(f)
            else:
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
            
            console.print("\n[bold green]✨ 모든 파이프라인이 성공적으로 완료되었습니다! ✨[/bold green]")
            
        except Exception as e:
            console.print(f"\n[bold red]❌ 파이프라인 중단 오류 발생: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc())

if __name__ == "__main__":
    pipeline = PokemonShortsPipeline()
    asyncio.run(pipeline.run())
