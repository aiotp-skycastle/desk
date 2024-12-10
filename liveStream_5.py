import os
import requests
import time
import subprocess
import shutil
import hashlib
import socket
import logging
import threading

from datetime import datetime


requests.packages.urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

# **로깅 설정**
logging.basicConfig(
    filename='./log/camera_log.txt',  # 로그 파일 이름
    level=logging.INFO,  # 로깅 수준
    format='%(asctime)s - %(levelname)s - %(message)s',  # 시간, 로그 수준, 메시지 형식
    datefmt='%Y-%m-%d %H:%M:%S'  # 시간 형식
)

# 서버 URL 설정
CAMERA_URL = "http://skycastle.cho0h5.org:8001/stream_desk/"

# HLS 파일 경로
HLS_DIR = "/home/ahnsukyum/camera"

# 디렉토리 초기화 함수
def initialize_directory():
    if os.path.exists(HLS_DIR):
        shutil.rmtree(HLS_DIR)
    os.makedirs(HLS_DIR)

# 파일 해시 계산 함수
def get_file_hash(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


ffmpeg_process = None

# ffmpeg 명령어 실행 함수
def generate_hls():
    global ffmpeg_process
    ffmpeg_command = [
        "ffmpeg",
        "-f", "v4l2",
        "-framerate", "15",
        "-video_size", "640x480",
        "-i", "/dev/video0",
        "-codec:v", "libx264",
        "-preset", "ultrafast",
        "-an",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "3",
        "-hls_flags", "delete_segments+split_by_time",
        "-hls_start_number_source", "epoch",  # 타임스탬프 기반 시작 번호
        os.path.join(HLS_DIR, "index.m3u8")
    ]
    try:
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logging.info("ffmpeg started successfully.")
        
        # stderr 로그를 실시간으로 기록
        def log_ffmpeg_output():
            for line in ffmpeg_process.stderr:
                line = line.strip()
                if "Error" in line or "Failed" in line:
                    logging.error(f"ffmpeg log: {line}")
        
        threading.Thread(target=log_ffmpeg_output, daemon=True).start()
        
    except Exception as e:
        logging.error(f"Error starting ffmpeg: {e}")

# HLS 파일 전송 함수
def upload_file(file_path, file_hashes):
    try:
        filename = os.path.basename(file_path)
        current_hash = get_file_hash(file_path)
        
        # .m3u8 파일이거나 파일 내용이 변경된 경우에만 업로드
        if file_path not in file_hashes or file_hashes[file_path] != current_hash or (filename.endswith('.m3u8') and file_hashes[file_path] != current_hash):
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f)}
                start_time = datetime.now()
                response = requests.post(CAMERA_URL, files=files)
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                if response.status_code in [200, 201]:
                    logging.info(f"Successfully uploaded: {file_path} (Duration: {duration:.2f} seconds)")
                    file_hashes[file_path] = current_hash
                else:
                    logging.error(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
        # elif filename.endswith('.m3u8') and file_hashes[file_path] != current_hash:
        #      with open(file_path, 'rb') as f:
        #         files = {'file': (filename, f)}
        #         start_time = datetime.now()
        #         response = requests.post(CAMERA_URL, files=files)
        #         end_time = datetime.now()
        #         duration = (end_time - start_time).total_seconds()
        #         if response.status_code in [200, 201]:
        #             logging.info(f"Successfully uploaded: {file_path} (Duration: {duration:.2f} seconds)")
        #             file_hashes[file_path] = current_hash
        #         else:
        #             logging.error(f"Failed to upload: {file_path}, Status code: {response.status_code}, Response: {response.text}")
        # else:
        #     logging.error(f"File not changed, skipping upload: {file_path}")
    except Exception as e:
        logging.error(f"Error uploading {file_path}: {e}")
   
def check_device():
    return os.path.exists("/dev/video0")
        
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
        if not check_device():
            logging.error("/dev/video0 is not available. Restarting ffmpeg...")
            if ffmpeg_process:
                ffmpeg_process.terminate()
            time.sleep(1)
            generate_hls()
            continue
        
        if ffmpeg_process and ffmpeg_process.poll() is not None:  # 프로세스 종료 확인
            logging.error("ffmpeg process terminated unexpectedly. Restarting...")
            generate_hls()  # 프로세스 재시작
        files = sorted(os.listdir(HLS_DIR))
        for file in files:
            file_path = os.path.join(HLS_DIR, file)
            if os.path.isfile(file_path):
                upload_file(file_path, file_hashes)
        
        # 오래된 파일 해시 제거
        current_files = set(os.path.join(HLS_DIR, f) for f in os.listdir(HLS_DIR))
        file_hashes = {k: v for k, v in file_hashes.items() if k in current_files}
        
        time.sleep(0.5)

