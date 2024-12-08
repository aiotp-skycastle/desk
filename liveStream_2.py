import os
import requests
import hashlib
import time
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
import threading
import multiprocessing
from datetime import datetime

# HLS 디렉토리 및 서버 URL 설정
HLS_DIR = "/home/ahnsukyum/groupProject/camera"
CAMERA_URL = "http://skycastle.cho0h5.org:8001/stream_desk/"

# 파일 해시 및 상태 추적
file_hashes = {}
file_mod_times = {}
changed_ts_files = set()
lock = threading.Lock()

# 로그 출력 함수
def log(message):
    print(f"[{datetime.now()}] {message}")

# 디렉토리 초기화 함수
def initialize_directory():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)
    log("Directory initialized.")

# ffmpeg 명령어 실행 함수
def generate_hls():
    initialize_directory()
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
        "-hls_start_number_source", "epoch",
        os.path.join(HLS_DIR, "index.m3u8")
    ]
    try:
        subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log("FFmpeg started.")
    except Exception as e:
        log(f"Error starting FFmpeg: {e}")

# 파일 해시 계산 함수
def get_file_hash(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# HLS 파일 전송 함수
def upload_files(files_to_upload):
    for file_path in files_to_upload:
        try:
            filename = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                start_time = datetime.now()
                response = requests.post(CAMERA_URL, files=files)
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                if response.status_code in [200, 201]:
                    log(f"Successfully uploaded: {file_path} (Duration: {duration:.2f} seconds)")
                else:
                    log(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
        except Exception as e:
            log(f"Error uploading {file_path}: {e}")

# 파일 모니터링 및 업로드 관리
def monitor_and_upload():
    global file_hashes, changed_ts_files
    with ThreadPoolExecutor(max_workers=4) as executor:  # 병렬 처리 워커 수 설정
        while True:
            files = sorted(os.listdir(HLS_DIR))
            new_ts_files = set()
            
            for file in files:
                file_path = os.path.join(HLS_DIR, file)
                if os.path.isfile(file_path):
                    with lock:
                        last_mod_time = os.path.getmtime(file_path)
                        if file_path not in file_mod_times or file_mod_times[file_path] != last_mod_time:
                            file_mod_times[file_path] = last_mod_time
                            
                            # 해시를 확인해 TS 파일 변경 여부 추적
                            if file.endswith('.ts'):
                                current_hash = get_file_hash(file_path)
                                if file_path not in file_hashes or file_hashes[file_path] != current_hash:
                                    file_hashes[file_path] = current_hash
                                    changed_ts_files.add(file_path)
                            
                            # m3u8 파일은 항상 포함
                            if file.endswith('.m3u8'):
                                new_ts_files.add(file_path)
            
            # 변화가 감지된 경우 TS 파일과 m3u8 파일 업로드
            if changed_ts_files:
                files_to_upload = list(changed_ts_files) + [os.path.join(HLS_DIR, "index.m3u8")]
                log(f"Uploading files: {files_to_upload}")
                executor.submit(upload_files, files_to_upload)
                with lock:
                    changed_ts_files.clear()  # 변화된 파일 목록 초기화

            # 오래된 파일 해시 제거
            with lock:
                current_files = set(os.path.join(HLS_DIR, f) for f in os.listdir(HLS_DIR))
                file_hashes = {k: v for k, v in file_hashes.items() if k in current_files}

            time.sleep(0.1)  # 루프 딜레이를 0.1초로 줄임

# 메인 함수에서 병렬 실행
if __name__ == "__main__":
    process1 = multiprocessing.Process(target=generate_hls)
    process2 = multiprocessing.Process(target=monitor_and_upload)

    log("Starting processes.")
    process1.start()
    process2.start()

    process1.join()
    process2.join()

