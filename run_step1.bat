@echo off
echo ===================================
echo 🚀 포켓몬 주식 쇼츠 자동화 - STEP 1
echo ===================================

echo 1. 필요한 파이썬 패키지를 설치합니다...
pip install -r requirements.txt

echo.
echo 2. STEP 1 (데이터 수집 및 대본 생성) 스크립트를 실행합니다...
python step1_data_script.py

pause
