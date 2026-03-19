import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import threading
import time
import schedule
import subprocess
from datetime import datetime

class StockShortsScheduler:
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 AI Stock Shorts Automator Pro")
        self.root.geometry("800x700")
        self.root.configure(bg="#1e2229")
        
        # 윈도우 중앙 배치
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width/2) - (800/2)
        y = (screen_height/2) - (700/2)
        self.root.geometry(f'+{int(x)}+{int(y)}')
        
        # 아이콘 설정 (아이콘 파일이 있을 경우)
        # if os.path.exists("icon.ico"): self.root.iconbitmap("icon.ico")
        
        self.config_file = "scheduler_config.json"
        self.is_running = False
        self.current_process = None
        
        self.setup_ui()
        self.load_config()
        
    def setup_ui(self):
        # 스타일 설정
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # 다크 테마 커스텀 클래스
        self.style.configure("Main.TFrame", background="#1e2229")
        self.style.configure("Card.TFrame", background="#2d3436", relief="flat")
        self.style.configure("TLabel", background="#1e2229", foreground="#ffffff", font=("Segoe UI", 10))
        self.style.configure("CardHeader.TLabel", background="#2d3436", foreground="#00a8ff", font=("Segoe UI", 12, "bold"))
        self.style.configure("Header.TLabel", background="#1e2229", foreground="#00d2ff", font=("Segoe UI", 24, "bold"))
        self.style.configure("Status.TLabel", background="#2d3436", foreground="#7f8c8d", font=("Consolas", 9))
        
        # 메인 컨테이너
        container = ttk.Frame(self.root, style="Main.TFrame", padding=35)
        container.pack(fill="both", expand=True)
        
        # 1. 헤더 영역
        header_frame = ttk.Frame(container, style="Main.TFrame")
        header_frame.pack(fill="x", pady=(0, 25))
        
        ttk.Label(header_frame, text="📊 AI STOCK SHORTS", style="Header.TLabel").pack(side="left")
        
        self.time_now_label = ttk.Label(header_frame, text="", font=("Segoe UI Semibold", 13), foreground="#9c88ff")
        self.time_now_label.pack(side="right", pady=10)
        self.update_clock()
        
        # 2. 메인 설정 카드 (시장별 설정)
        cards_frame = ttk.Frame(container, style="Main.TFrame")
        cards_frame.pack(fill="x", pady=10)
        
        # --- 한국 시장 설정 ---
        kr_card = ttk.Frame(cards_frame, style="Card.TFrame", padding=20)
        kr_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ttk.Label(kr_card, text="🇰🇷 KOREA MARKET", style="CardHeader.TLabel", foreground="#ff4757").pack(anchor="w")
        ttk.Label(kr_card, text="오늘의 장 마감 브리핑", background="#2d3436", foreground="#bdc3c7", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 10))
        
        self.kr_time_var = tk.StringVar(value="16:00")
        kr_entry = tk.Entry(kr_card, textvariable=self.kr_time_var, font=("Segoe UI Bold", 20), bg="#1e2229", fg="#ffffff", 
                           insertbackground="white", width=8, justify="center", bd=0)
        kr_entry.pack(pady=10)
        
        # --- 미국 시장 설정 ---
        us_card = ttk.Frame(cards_frame, style="Card.TFrame", padding=20)
        us_card.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        ttk.Label(us_card, text="🇺🇸 USA MARKET", style="CardHeader.TLabel", foreground="#3742fa").pack(anchor="w")
        ttk.Label(us_card, text="오늘의 시장 요약 브리핑", background="#2d3436", foreground="#bdc3c7", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 10))
        
        self.us_time_var = tk.StringVar(value="07:00")
        us_entry = tk.Entry(us_card, textvariable=self.us_time_var, font=("Segoe UI Bold", 20), bg="#1e2229", fg="#ffffff", 
                           insertbackground="white", width=8, justify="center", bd=0)
        us_entry.pack(pady=10)
        
        # 3. 제어 패널
        control_frame = ttk.Frame(container, style="Main.TFrame", padding=(0, 30))
        control_frame.pack(fill="x")
        
        # 메인 스위치 버튼
        self.start_btn = tk.Button(control_frame, text="▶ START AUTO-SCHEDULER", command=self.toggle_scheduler,
                                  bg="#2ed573", fg="white", font=("Segoe UI Black", 13), relief="flat", padx=30, pady=15, 
                                  activebackground="#7bed9f", activeforeground="white", cursor="hand2")
        self.start_btn.pack(side="left")
        
        # 즉시 실행 버튼들
        btn_frame = ttk.Frame(control_frame, style="Main.TFrame")
        btn_frame.pack(side="right")
        
        self.run_kr_btn = tk.Button(btn_frame, text="RUN KR NOW", command=lambda: self.run_now("KR"),
                                   bg="#2f3542", fg="#ffffff", font=("Segoe UI Bold", 9), relief="flat", padx=15, pady=10, cursor="hand2")
        self.run_kr_btn.pack(side="right", padx=(5, 0))
        
        self.run_us_btn = tk.Button(btn_frame, text="RUN US NOW", command=lambda: self.run_now("US"),
                                   bg="#2f3542", fg="#ffffff", font=("Segoe UI Bold", 9), relief="flat", padx=15, pady=10, cursor="hand2")
        self.run_us_btn.pack(side="right")
        
        # 4. 로그 콘솔
        console_frame = ttk.Frame(container, style="Main.TFrame")
        console_frame.pack(fill="both", expand=True)
        
        ttk.Label(console_frame, text="🖥️ SYSTEM LOG", font=("Segoe UI", 10, "bold"), foreground="#a4b0be").pack(anchor="w", pady=(0, 5))
        
        self.log_text = tk.Text(console_frame, bg="#101419", fg="#2ed573", font=("Consolas", 10), height=15, 
                               relief="flat", padx=15, pady=15, insertbackground="white")
        self.log_text.pack(fill="both", expand=True)
        
        # 스크롤바 추가
        scrollbar = ttk.Scrollbar(self.log_text, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # 상태바
        self.status_var = tk.StringVar(value="Status: Monitoring...")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, font=("Consolas", 9), anchor="w", 
                                  padx=15, pady=8, bg="#2f3542", fg="#a4b0be")
        self.status_bar.pack(side="bottom", fill="x")

    def update_clock(self):
        now = datetime.now().strftime("%Y년 %m월 %d일 %H:%M:%S")
        self.time_now_label.config(text=now)
        self.root.after(1000, self.update_clock)

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = "#2ed573" # 기본 (초록)
        if "ERROR" in level or "❌" in message: color = "#ff4757" # 빨강
        elif "WARNING" in level or "⚠️" in message: color = "#eccc68" # 노랑
        elif "PIPELINE" in level: color = "#70a1ff" # 파랑
        
        self.log_text.tag_config(level, foreground=color)
        self.log_text.insert("end", f"[{timestamp}] ", "TIME")
        self.log_text.insert("end", f"{message}\n", level)
        self.log_text.see("end")
        
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.kr_time_var.set(config.get("KR", "16:00"))
                    self.us_time_var.set(config.get("US", "07:00"))
                    self.log("✅ 이전 설정을 성공적으로 불러왔습니다.")
            except Exception as e:
                self.log(f"⚠️ 설정 로드 실패: {e}", "WARNING")

    def save_config(self):
        config = {"KR": self.kr_time_var.get(), "US": self.us_time_var.get()}
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.log(f"❌ 설정 저장 실패: {e}", "ERROR")

    def run_pipeline(self, market):
        self.log(f"🚀 [{market}] 파이프라인 가동을 시작합니다...", "PIPELINE")
        try:
            # 파이썬 실행 경로 감지 (현재 환경의 python.exe 우선 시도)
            python_path = sys.executable
            
            # CMD 호출 (실시간 로그 출력을 위해 부모 프로세스의 stdout을 비동기로 읽음)
            cmd = [python_path, "shorts_pipeline.py", "--market", market]
            
            # Windows에서 창 숨기기 설정
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.current_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                shell=False, # 보안 및 안정성을 위해 shell=False 추천
                text=True, 
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo
            )
            
            if self.current_process.stdout:
                for line in iter(self.current_process.stdout.readline, ""):
                    line = line.strip()
                    if line: 
                        # 주요 키워드에 따라 로그 레벨링
                        if "완료" in line or "성공" in line: lvl = "INFO"
                        elif "❌" in line or "실패" in line: lvl = "ERROR"
                        elif "⚠️" in line: lvl = "WARNING"
                        else: lvl = "INFO"
                        self.log(f"[{market}] {line}", lvl)
            
            self.current_process.wait()
            if self.current_process.returncode == 0:
                self.log(f"✨ [{market}] 모든 공정이 완료되었습니다.", "INFO")
                # 토스트 알림 (선택 사항)
            else:
                self.log(f"⚠️ [{market}] 파이프라인 종료 (코드: {self.current_process.returncode})", "WARNING")
        except Exception as e:
            self.log(f"❌ 시스템 오류 발생: {e}", "ERROR")
        finally:
            self.current_process = None

    def run_now(self, market):
        if messagebox.askyesno("즉시 실행", f"지금 바로 {market} 시장 영상 제작을 시작하시겠습니까?\n(수동 실행은 업로드 한도에 주의하세요)"):
            threading.Thread(target=self.run_pipeline, args=(market,), daemon=True).start()
        
    def toggle_scheduler(self):
        if not self.is_running:
            # 시간 형식 검증
            try:
                kr_t = self.kr_time_var.get().strip()
                us_t = self.us_time_var.get().strip()
                datetime.strptime(kr_t, "%H:%M")
                datetime.strptime(us_t, "%H:%M")
            except ValueError:
                messagebox.showerror("형식 오류", "시간은 HH:MM (예: 16:30) 형식으로 입력해 주세요.")
                return

            self.save_config()
            self.is_running = True
            
            # UI 상태 업데이트
            self.start_btn.config(text="⏹ STOP SCHEDULER", bg="#ff4757", activebackground="#ff6b81")
            self.status_var.set(f"● 스케줄러 작동 중 (KR: {kr_t} | US: {us_t})")
            self.status_bar.config(fg="#2ed573")
            
            self.log(f"📡 자동 실행 스케줄러가 활성화되었습니다. (KR: {kr_t}, US: {us_t})")
            threading.Thread(target=self.scheduler_loop, daemon=True).start()
        else:
            self.is_running = False
            self.start_btn.config(text="▶ START AUTO-SCHEDULER", bg="#2ed573", activebackground="#7bed9f")
            self.status_var.set("Status: Monitoring (Ready)")
            self.status_bar.config(fg="#a4b0be")
            self.log("⏹️ 스케줄러가 중지되었습니다.")
            schedule.clear()

    def scheduler_loop(self):
        schedule.clear()
        kr_t = self.kr_time_var.get().strip()
        us_t = self.us_time_var.get().strip()
        
        schedule.every().day.at(kr_t).do(self.run_pipeline, "KR")
        schedule.every().day.at(us_t).do(self.run_pipeline, "US")
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(10)

if __name__ == "__main__":
    # 고해상도 모니터 대응
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    
    root = tk.Tk()
    app = StockShortsScheduler(root)
    root.mainloop()
