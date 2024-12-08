import os
import requests
import time
import subprocess
import shutil

# 서버 URL 설정
CAMERA_URL = "https://skycastle.cho0h5.org/stream_desk/"

# HLS 파일 경로
HLS_DIR = "/home/ahnsukyum/groupProject/camera"

# 디렉토리 초기화 함수
def initialize_directory():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)

# ffmpeg 명령어 실행 함수
def generate_hls():
    ffmpeg_command = [
        "ffmpeg",
        "-f", "v4l2",                      # Video4Linux2 포맷 사용
        "-i", "/dev/video0",               # 카메라 장치
        "-codec:v", "libx264",             # H.264 인코딩
        "-preset", "ultrafast",            # 빠른 인코딩
        "-f", "hls",                       # HLS 포맷
        "-hls_time", "1",                  # 세그먼트 길이 (1초)
        "-hls_list_size", "3",             # 최신 3개의 세그먼트 유지
        "-hls_flags", "delete_segments+split_by_time",  # 오래된 세그먼트 삭제
        "-hls_segment_filename", os.path.join(HLS_DIR, "segment%07d.ts"),  # 세그먼트 파일 이름 형식
        "-start_number", "0",              # 시작 번호를 0으로 설정
        os.path.join(HLS_DIR, "index.m3u8")  # 출력 파일 경로
    ]
    try:
        subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("ffmpeg started successfully.")
    except Exception as e:
        print(f"Error starting ffmpeg: {e}")

# HLS 파일 전송 함수
def upload_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            response = requests.post(CAMERA_URL, files=files)
            
            if response.status_code in [200, 201]:
                print(f"Successfully uploaded: {file_path}")
            else:
                print(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")

# 파일 전송 루프
if __name__ == "__main__":
    # 디렉토리 초기화
    initialize_directory()

    # ffmpeg 실행
    generate_hls()

    # HLS 파일 전송 루프
    while True:
        files = sorted(os.listdir(HLS_DIR))
        for file in files:
            file_path = os.path.join(HLS_DIR, file)
            if os.path.isfile(file_path):
                upload_file(file_path)
        
        time.sleep(1)
