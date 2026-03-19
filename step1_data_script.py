import yfinance as yf
import json
import os
import datetime
import google.generativeai as genai

# ==========================================
# ⚙️ 설정 값
# ==========================================
# GEMINI_API_KEY 환경 변수가 설정되어 있어야 합니다.
# os.environ["GEMINI_API_KEY"] = "AIzaSy..."
# 또는 직접 키를 하드코딩하려면 아래 줄의 주석을 해제하고 키를 넣으세요.
# genai.configure(api_key="여기에_GEMINI_API_KEY_입력")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 관측할 주요 나스닥 대표 종목 리스트 (필요에 따라 추가/변경 가능)
WATCHLIST = ['QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL', 'AMD', 'AVGO']

def fetch_market_data():
    """yfinance를 이용해 당일/전일 나스닥 주요 종목 시세와 거래량, 그리고 주요 뉴스를 수집합니다."""
    print("📈 나스닥 시장 데이터를 수집하는 중...")
    market_summary = []
    news_summary = []
    
    for ticker_symbol in WATCHLIST:
        try:
            ticker = yf.Ticker(ticker_symbol)
            # 최근 2일 데이터 가져오기 (전일 대비 등락률 계산을 위함)
            hist = ticker.history(period="2d")
            
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[0]
                current_close = hist['Close'].iloc[1]
                volume = hist['Volume'].iloc[1]
                pct_change = ((current_close - prev_close) / prev_close) * 100
                
                market_summary.append({
                    "ticker": ticker_symbol,
                    "price_change_pct": round(pct_change, 2),
                    "volume": int(volume)
                })
                
                # 시가총액이 큰 종목의 최근 뉴스 확인
                if ticker_symbol in ['QQQ', 'NVDA', 'TSLA']:
                    recent_news = ticker.news
                    if recent_news:
                        news_summary.append(f"[{ticker_symbol} 이슈] {recent_news[0]['title']}")
        except Exception as e:
            print(f"⚠️ {ticker_symbol} 데이터 수집 실패: {e}")
            
    # 거래량(Volume) 기준으로 내림차순 정렬하여 상위 5개 추출
    top_volume_stocks = sorted(market_summary, key=lambda x: x['volume'], reverse=True)[:5]
    
    return {
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "top_stocks": top_volume_stocks,
        "market_news": news_summary
    }

def generate_script_and_prompts(market_data):
    """Google Gemini API를 호출하여 포켓몬 배틀 비유 형식의 쇼츠 대본과 프롬프트를 JSON으로 생성합니다."""
    print("🤖 Gemini 1.5 Pro를 통해 대본과 이미지 프롬프트를 생성 중입니다...")
    
    system_instruction = """
    너는 유튜브 쇼츠 대본 스토리텔러이자, 포켓몬스터 스타일 배틀 컨셉의 천재적인 기획자야.
    내가 제공하는 '오늘의 미국 나스닥 식생(주식 시장) 데이터'를 바탕으로,
    1분 이내의 박진감 넘치는 쇼츠 대본을 작성해.
    
    [규칙]
    1. 주식 종목(예: 엔비디아, 테슬라, 애플 등)의 등락률과 거래량을 마치 '오리지널 몬스터'들의 기술 사용이나 전투 상황에 비유할 것. (절대 기존 포켓몬의 이름(리자몽, 피카츄 등)은 저작권 때문에 쓰지 말고 창작해. '녹색 눈방울 마법사 몬스터(엔비디아)', '전기를 뿜는 은색 자동차 탈것 몬스터(테슬라)' 등으로 묘사 후 주식 이름 언급)
    2. 시청자가 지루하지 않게 긴장감 있고 빠른 템포의 나레이션 구성.
    3. 각 대본의 나레이션 라인마다 비디오(이미지)를 생성할 수 있는 영어 프롬프트(Image Prompt)를 1:1로 매칭해서 제공해.
       - 이미지 프롬프트는 2D 애니메이션, 역동적인 몬스터 캡처 전투 스타일, 귀엽고 화려한 이펙트를 필수로 포함해.
    4. 반드시 아래 JSON 형식으로만 결과값을 출력해! 포맷을 깨지마.

    [JSON 출력 구조 예시]
    {
      "youtube_metadata": {
        "title": "쇼츠 제목 (이모지 포함)",
        "description": "설명란 내용",
        "tags": ["#Shorts", "#주식", "#나스닥", "#종목티커1", "#종목티커2"]
      },
      "scenes": [
        {
          "scene_number": 1,
          "narration": "나스닥 생태계가 폭주하고 있습니다! 오늘 엄청난 거래량을 뿜어내며 등장한 건 바로 엔비디아!",
          "image_prompt": "A 2D anime style scene, monster capture game battle, a giant green mystical creature with glowing eyes roaring confidently, surrounded by green digital charts and upward arrows, dynamic and cool."
        }
      ]
    }
    """

    user_prompt = f"다음은 수집된 오늘의 나스닥 시장 데이터야. 이걸 바탕으로 위의 JSON 형식대로 대본을 만들어줘.\n\n{json.dumps(market_data, ensure_ascii=False, indent=2)}"

    # Gemini 1.5 Pro (또는 Flash) 모델 선택
    model = genai.GenerativeModel('gemini-1.5-pro', system_instruction=system_instruction)

    # JSON 응답을 강제하기 위한 설정
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.7
    )

    response = model.generate_content(
        user_prompt,
        generation_config=generation_config
    )

    result_json = response.text
    return json.loads(result_json)

def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ 오류: GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
        print("구글 AI Studio에서 API 키를 발급받은 후 설정해주세요.")
        return

    # 1. 데이터 수집
    market_data = fetch_market_data()
    print("✅ 데이터 수집 완료:\n", json.dumps(market_data, ensure_ascii=False, indent=2))
    print("-" * 50)
    
    # 2. Gemini 로 대본/프롬프트 생성
    try:
        script_data = generate_script_and_prompts(market_data)
        
        # 3. 파일로 저장
        output_filename = f"script_{market_data['date']}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=4)
            
        print(f"🎉 성공! 대본과 프롬프트가 '{output_filename}' 파일로 저장되었습니다.")
    except Exception as e:
        print(f"❌ 대본 생성 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
