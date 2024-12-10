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
CAMERA_URL = "http://skycastle.cho0h5.org/stream_desk/"

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
    try:
        if os.path.exists(HLS_DIR):
            shutil.rmtree(HLS_DIR)
        os.makedirs(HLS_DIR)
        log("Directory initialized.")
    except Exception as e:
        log(f"Error initializing directory: {e}")

# ffmpeg 명령어 실행 함수
def generate_hls():
    try:
        initialize_directory()
        ffmpeg_command = [
            "ffmpeg",
            "-f", "v4l2",
            "-i", "/dev/video0",
            "-codec:v", "libx264",
            "-preset", "ultrafast",
            "-f", "hls",
            "-hls_time", "4",
            "-hls_list_size", "3",
            "-hls_flags", "delete_segments+split_by_time",
            "-framerate", "15",
            "-video_size", "640x480",
            "-hls_start_number_source", "epoch",
            os.path.join(HLS_DIR, "index.m3u8")
        ]
        subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log("FFmpeg started.")
    except FileNotFoundError as e:
        log(f"FFmpeg executable not found: {e}")
    except Exception as e:
        log(f"Error starting FFmpeg: {e}")

# 파일 해시 계산 함수
def get_file_hash(file_path):
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        log(f"Error calculating hash for {file_path}: {e}")
        return None

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
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            while True:
                files = sorted(os.listdir(HLS_DIR))
                new_ts_files = set()
                log(f"Monitoring directory. Current files: {files}")
                
                for file in files:
                    file_path = os.path.join(HLS_DIR, file)
                    if os.path.isfile(file_path):
                        with lock:
                            last_mod_time = os.path.getmtime(file_path)
                            if file_path not in file_mod_times or file_mod_times[file_path] != last_mod_time:
                                file_mod_times[file_path] = last_mod_time
                                
                                if file.endswith('.ts'):
                                    current_hash = get_file_hash(file_path)
                                    if current_hash and (file_path not in file_hashes or file_hashes[file_path] != current_hash):
                                        file_hashes[file_path] = current_hash
                                        changed_ts_files.add(file_path)
                                
                                if file.endswith('.m3u8'):
                                    new_ts_files.add(file_path)
                
                if changed_ts_files:
                    files_to_upload = list(changed_ts_files) + [os.path.join(HLS_DIR, "index.m3u8")]
                    log(f"Uploading files: {files_to_upload}")
                    executor.submit(upload_files, files_to_upload)
                    with lock:
                        changed_ts_files.clear()

                with lock:
                    current_files = set(os.path.join(HLS_DIR, f) for f in os.listdir(HLS_DIR))
                    file_hashes = {k: v for k, v in file_hashes.items() if k in current_files}

                time.sleep(1)  # 루프 주기를 1초로 조정
    except Exception as e:
        log(f"Error in monitor_and_upload: {e}")

# 메인 함수에서 병렬 실행
if __name__ == "__main__":
    try:
        log("Starting processes.")
        process1 = multiprocessing.Process(target=generate_hls)
        process2 = multiprocessing.Process(target=monitor_and_upload)

        process1.start()
        process2.start()

        process1.join()
        process2.join()
    except Exception as e:
        log(f"Main process error: {e}")

