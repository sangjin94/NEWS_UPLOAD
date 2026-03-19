import json
import os
import glob
import asyncio
import urllib.request

# TTS 라이브러리 (비동기, 고품질 무료 TTS)
# pip install edge-tts 필요
import edge_tts

# ==========================================
# ⚙️ 설정 값
# ==========================================
# 음성 설정 (edge-tts 사용, 한국어 남성 목소리 추천: ko-KR-InJoonNeural)
TTS_VOICE = "ko-KR-InJoonNeural"

# 이미지 생성 (예: OpenAI DALL-E 연동을 위한 키)
# os.environ["OPENAI_API_KEY"] = "sk-..."
OUTPUT_DIR = "media_assets"

def get_latest_script():
    """가장 최근에 생성된 JSON 대본 파일을 찾습니다."""
    files = glob.glob("script_*.json")
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

async def generate_audio(text, output_path):
    """edge-tts를 사용하여 나레이션을 음성 파일로 변환합니다."""
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)
    print(f"🔊 음성 생성 완료: {output_path}")

def generate_image_dummy(prompt, output_path):
    """
    이미지 생성 API(Imagen 3 또는 DALL-E) 호출용 함수입니다.
    현재는 API 설정 전이므로 더미 이미지를 다운로드하거나 함수 형태만 남겨둡니다.
    """
    # 실제 연동 시 아래 주석된 형식처럼 API를 호출하도록 구현하면 됩니다.
    # 예시 (OpenAI DALL-E 3)
    # from openai import OpenAI
    # client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    # response = client.images.generate(
    #     model="dall-e-3", prompt=prompt, size="1024x1024", quality="standard", n=1
    # )
    # image_url = response.data[0].url
    # urllib.request.urlretrieve(image_url, output_path)
    
    # 더미 이미지 다운로드 로직 (가상의 플레이스홀더)
    print(f"🎨 이미지 프롬프트: {prompt}")
    placeholder_url = f"https://via.placeholder.com/1024x1024.png?text=Scene+Image"
    urllib.request.urlretrieve(placeholder_url, output_path)
    print(f"🖼️ 이미지 생성 완료(더미): {output_path}")

async def main():
    script_file = get_latest_script()
    if not script_file:
        print("❌ 스크립트 파일을 찾을 수 없습니다. STEP 1을 먼저 실행해주세요.")
        return

    print(f"📂 스크립트 로드: {script_file}")
    with open(script_file, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    scenes = script_data.get("scenes", [])
    print(f"⏳ 총 {len(scenes)}개의 씬(Scene) 미디어 파일 생성을 시작합니다...")

    for scene in scenes:
        scene_num = scene["scene_number"]
        narration = scene.get("narration", "")
        image_prompt = scene.get("image_prompt", "")

        # 파일 경로 설정
        audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_num}.mp3")
        image_path = os.path.join(OUTPUT_DIR, f"scene_{scene_num}.png")

        # 1. TTS 오디오 생성 (edge-tts)
        if narration:
            await generate_audio(narration, audio_path)
        
        # 2. 씬 이미지 생성
        if image_prompt:
            generate_image_dummy(image_prompt, image_path)

    print("🎉 STEP 2 미디어 소스 생성이 모두 완료되었습니다!")
    print(f"결과물은 '{OUTPUT_DIR}' 폴더를 확인하세요.")

if __name__ == "__main__":
    asyncio.run(main())
