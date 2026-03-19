import os
import json
import glob
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

# ==========================================
# ⚙️ 설정 값
# ==========================================
# GCP 콘솔에서 다운로드한 OAuth 2.0 클라이언트 인증 정보 파일 경로
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
VIDEO_FILE = "final_shorts.mp4"

def get_latest_script():
    files = glob.glob("script_*.json")
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def get_authenticated_service():
    """사용자 인증을 통해 YouTube Data API 서비스 객체를 반환합니다."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"❌ 오류: '{CLIENT_SECRETS_FILE}' 파일이 없습니다.")
        print("구글 클라우드 콘솔에서 YouTube Data API v3를 활성화하고 OAuth 클라이언트 ID를 다운로드 하세요.")
        return None

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    # 로컬 브라우저를 열어 인증 수행
    credentials = flow.run_local_server(port=0)
    return build('youtube', 'v3', credentials=credentials)

def upload_video():
    """video_file을 바탕으로 YouTube에 영상을 업로드합니다."""
    if not os.path.exists(VIDEO_FILE):
        print(f"❌ 업로드할 영상 파일('{VIDEO_FILE}')을 찾을 수 없습니다. STEP 3를 확인하세요.")
        return
        
    script_file = get_latest_script()
    if not script_file:
        print("❌ 스크립트 파일을 찾을 수 없어 메타데이터를 불러오지 못했습니다.")
        return

    # 메타데이터 로드
    with open(script_file, "r", encoding="utf-8") as f:
        script_data = json.load(f)
        
    meta = script_data.get("youtube_metadata", {})
    title = meta.get("title", "당일 나스닥 포켓몬 배틀 브리핑 #Shorts")
    description = meta.get("description", "나스닥 식생에서 벌어진 포켓몬스터 몬스터 배틀 비유 브리핑입니다.")
    tags = meta.get("tags", ["#Shorts", "#주식", "#나스닥"])

    print("🔑 유튜브 업로드 인증을 진행합니다... 브라우저 창을 확인하세요.")
    youtube = get_authenticated_service()
    if not youtube:
        return

    print(f"🚀 영상 업로드를 시작합니다: {title}")
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': '28' # 28: Science & Technology (필요시 변경, 24: Entertainment)
        },
        'status': {
            'privacyStatus': 'private', # 테스트용 비공개 (public으로 변경 가능)
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(VIDEO_FILE, mimetype='video/mp4', resumable=True)

    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"📤 업로드 진행 중: {int(status.progress() * 100)}%")

    print(f"🎉 성공! 영상이 유튜브에 업로드되었습니다.")
    print(f"🔗 링크: https://youtu.be/{response['id']}")

if __name__ == '__main__':
    upload_video()
