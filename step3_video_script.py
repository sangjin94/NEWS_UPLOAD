import json
import os
import glob
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip, concatenate_videoclips

# Windows 환경에서는 ImageMagick 설치 후 아래 경로를 알맞게 수정해야 합니다. (TextClip 렌더링 용)
# os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"

MEDIA_DIR = "media_assets"
OUTPUT_VIDEO = "final_shorts.mp4"
RESOLUTION = (1080, 1920) # 9:16 Shorts 해상도

def get_latest_script():
    files = glob.glob("script_*.json")
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def create_scene_clip(scene_data):
    """오디오와 이미지를 합쳐 하나의 씬(Scene) 클립으로 만듭니다."""
    scene_num = scene_data["scene_number"]
    narration_text = scene_data.get("narration", "")
    
    audio_path = os.path.join(MEDIA_DIR, f"scene_{scene_num}.mp3")
    image_path = os.path.join(MEDIA_DIR, f"scene_{scene_num}.png")

    if not os.path.exists(audio_path) or not os.path.exists(image_path):
        print(f"⚠️ 씬 {scene_num}의 미디어 파일을 찾을 수 없어 건너뜁니다.")
        return None

    # 오디오 로드 및 길이 계산
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # 이미지 로드 후 오디오 길이에 맞춤, 해상도 크롭/리사이즈 (9:16 중앙)
    # resize_width 혹은 resize_height 중 맞춰서 자름
    img_clip = ImageClip(image_path).set_duration(duration)
    img_clip = img_clip.resize(height=RESOLUTION[1])
    img_clip = img_clip.crop(x_center=img_clip.w/2, width=RESOLUTION[0])

    # 자막(TextClip) 생성 (한글 폰트 지정 필요, 예: 'Malgun-Gothic')
    try:
        txt_clip = TextClip(
            narration_text,
            fontsize=60,
            color='white',
            bg_color='black',
            font='Malgun-Gothic-Bold',
            method='caption',
            size=(RESOLUTION[0] - 100, None)
        ).set_position(('center', 'bottom')).set_duration(duration)
        
        # 합치기
        video = CompositeVideoClip([img_clip, txt_clip.set_position(("center", RESOLUTION[1]-250))])
    except Exception as e:
        print(f"⚠️ 자막 렌더링에 실패하여 이미지만 사용합니다: {e}")
        video = img_clip

    # 오디오 병합
    video = video.set_audio(audio_clip)
    return video

def main():
    script_file = get_latest_script()
    if not script_file:
        print("❌ 스크립트 파일을 찾을 수 없습니다.")
        return

    with open(script_file, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    scenes = script_data.get("scenes", [])
    clips = []

    print("🎬 영상 클립을 합성하는 중...")
    for scene in scenes:
        clip = create_scene_clip(scene)
        if clip:
            clips.append(clip)

    if not clips:
        print("❌ 렌더링할 클립이 없습니다.")
        return

    # 씬 이어 붙이기
    final_video = concatenate_videoclips(clips, method="compose")

    print("🛠️ 최종 영상을 렌더링합니다. (시간이 걸릴 수 있습니다...)")
    final_video.write_videofile(OUTPUT_VIDEO, fps=24, codec="libx264", audio_codec="aac")
    print(f"🎉 성공! 영상이 '{OUTPUT_VIDEO}'로 렌더링 되었습니다.")

if __name__ == "__main__":
    main()
