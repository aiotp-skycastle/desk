import os
import requests
import time
import subprocess
import shutil
import hashlib
from concurrent.futures import ThreadPoolExecutor
import threading

# 서버 URL 설정
CAMERA_URL = "http://skycastle.cho0h5.org:8001/stream_desk/"

# HLS 파일 경로
HLS_DIR = "/home/ahnsukyum/groupProject/camera"

# 파일 해시 및 수정 시간 추적
file_hashes = {}
file_mod_times = {}
lock = threading.Lock()

# 디렉토리 초기화 함수
def initialize_directory():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)

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

# 파일 해시 계산 함수
def get_file_hash(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# HLS 파일 전송 함수


def upload_file(file_path):
    try:
        filename = os.path.basename(file_path)
        current_hash = get_file_hash(file_path)
        
        with lock:
            if file_path not in file_hashes:
                print(f"New file detected: {file_path}")
            elif file_hashes[file_path] == current_hash:
                print(f"File unchanged, skipping upload: {file_path} (hash: {current_hash})")
            else:
                print(f"File changed, preparing upload: {file_path} (old hash: {file_hashes[file_path]}, new hash: {current_hash})")
            
            # 파일 내용이 변경된 경우에만 업로드
            if file_path not in file_hashes or file_hashes[file_path] != current_hash:
                with open(file_path, 'rb') as f:
                    files = {'file': (filename, f)}
                    response = requests.post(CAMERA_URL, files=files)
                    
                    if response.status_code in [200, 201]:
                        print(f"Successfully uploaded: {file_path}")
                        file_hashes[file_path] = current_hash
                    else:
                        print(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")

def monitor_and_upload():
    global file_hashes
    with ThreadPoolExecutor(max_workers=4) as executor:  # 병렬 처리 워커 수 설정
        while True:
            files = sorted(os.listdir(HLS_DIR))
            for file in files:
                file_path = os.path.join(HLS_DIR, file)
                if os.path.isfile(file_path):
                    with lock:
                        last_mod_time = os.path.getmtime(file_path)
                        if file_path not in file_mod_times or file_mod_times[file_path] != last_mod_time:
                            file_mod_times[file_path] = last_mod_time
                            executor.submit(upload_file, file_path)

            # 오래된 파일 해시 제거
            with lock:
                current_files = set(os.path.join(HLS_DIR, f) for f in os.listdir(HLS_DIR))
                file_hashes = {k: v for k, v in file_hashes.items() if k in current_files}

            time.sleep(0.1)  # 루프 딜레이를 0.1초로 줄임



if __name__ == "__main__":
    # 디렉토리 초기화
    initialize_directory()

    # ffmpeg 실행
    generate_hls()

    # 파일 모니터링 및 전송 루프 시작
    monitor_and_upload()

