import os
import requests
import time
import subprocess
import shutil
import hashlib


# 서버 URL 설정
CAMERA_URL = "http://skycastle.cho0h5.org:8001/stream_desk/"

# HLS 파일 경로
HLS_DIR = "/home/ahnsukyum/groupProject/camera"

# 디렉토리 초기화 함수
def initialize_directory():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)

# 파일 해시 계산 함수
def get_file_hash(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# ffmpeg 명령어 실행 함수
def generate_hls():
    ffmpeg_command = [
        "ffmpeg",
        "-f", "v4l2",
        "-i", "/dev/video0",
        "-codec:v", "libx264",
        "-preset", "ultrafast",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "2",
        "-hls_flags", "delete_segments+split_by_time",
        "-framerate", "15",
        "-video_size", "640x480",
        "-hls_start_number_source", "epoch",  # 타임스탬프 기반 시작 번호
        os.path.join(HLS_DIR, "index.m3u8")
    ]
    try:
        subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("ffmpeg started successfully.")
    except Exception as e:
        print(f"Error starting ffmpeg: {e}")

# HLS 파일 전송 함수
def upload_file(file_path, file_hashes):
    try:
        filename = os.path.basename(file_path)
        current_hash = get_file_hash(file_path)
        
        # .m3u8 파일이거나 파일 내용이 변경된 경우에만 업로드
        if filename.endswith('.m3u8') or file_path not in file_hashes or file_hashes[file_path] != current_hash:
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                response = requests.post(CAMERA_URL, files=files)
                
                if response.status_code in [200, 201]:
                    print(f"Successfully uploaded: {file_path}")
                    file_hashes[file_path] = current_hash
                else:
                    print(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
        else:
            print(f"File not changed, skipping upload: {file_path}")
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")
        
# 파일 전송 루프
if __name__ == "__main__":
    # 디렉토리 초기화
    initialize_directory()

    # ffmpeg 실행
    generate_hls()

    # 파일 해시 추적
    file_hashes = {}

    # HLS 파일 전송 루프
    while True:
        files = sorted(os.listdir(HLS_DIR))
        for file in files:
            file_path = os.path.join(HLS_DIR, file)
            if os.path.isfile(file_path):
                upload_file(file_path, file_hashes)
        
        # 오래된 파일 해시 제거
        current_files = set(os.path.join(HLS_DIR, f) for f in os.listdir(HLS_DIR))
        file_hashes = {k: v for k, v in file_hashes.items() if k in current_files}
        



