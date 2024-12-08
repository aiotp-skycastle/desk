import RPi.GPIO as GPIO
import time
import requests
import socket
import urllib3
from RPLCD.i2c import CharLCD
import sys
import logging
from datetime import datetime, timezone, timedelta
import threading

# 전역 변수로 타이머 객체 선언
lcd_reset_timer = None


def reset_lcd_display():
    global lcd_reset_timer
    lcd_reset_timer = None
    check_study_time()


# 로깅 설정 - 콘솔과 파일 모두에 로그 출력
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('led_switch_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)

def print_pin_status(pin, name):
    """핀 상태를 출력하는 헬퍼 함수"""
    try:
        state = GPIO.input(pin)
        logging.info(f"{name} (Pin {pin}) 상태: {'HIGH' if state else 'LOW'}")
    except Exception as e:
        logging.error(f"{name} 상태 읽기 실패: {e}")

def setup_gpio():
    logging.info("GPIO 초기화 시작...")
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)

    # LED 핀 설정
    led_pins = [12, 33, 35]  # GPIO 18, 23, 24의 물리적 핀 번호
    for i, pin in enumerate(led_pins):
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
            logging.info(f"LED {i+1} (Pin {pin}) 초기화 완료")
        except Exception as e:
            logging.error(f"LED {i+1} (Pin {pin}) 초기화 실패: {e}")

    # 스위치 핀 설정
    switch_pins = [(11, "스위치 1"), (36, "스위치 2")]
    for pin, name in switch_pins:
        try:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            logging.info(f"{name} (Pin {pin}) 초기화 완료")
            print_pin_status(pin, name)
        except Exception as e:
            logging.error(f"{name} (Pin {pin}) 초기화 실패: {e}")

    # 부저 핀 설정
    try:
        GPIO.setup(37, GPIO.OUT)
        logging.info("부저 (Pin 37) 초기화 완료")
    except Exception as e:
        logging.error(f"부저 초기화 실패: {e}")
    
    logging.info("GPIO 초기화 완료")
    return led_pins

def setup_lcd():
    logging.info("LCD 초기화 시작...")
    try:
        lcd = CharLCD('PCF8574', 0x3F)
        logging.info("LCD 초기화 성공")
        return lcd
    except Exception as e:
        logging.error(f"LCD 초기화 실패: {e}")
        return None

def resolve_ip(domain):
    logging.info(f"도메인 {domain}의 IP 주소 조회 중...")
    try:
        addr_info = socket.getaddrinfo(domain, None, socket.AF_INET)
        ip = addr_info[0][4][0]
        logging.info(f"도메인 {domain}의 IPv4 주소 조회 성공: {ip}")
        return ip
    except Exception as e:
        logging.error(f"DNS 조회 실패: {e}")
        return None

def make_request():
    domain = 'skycastle.cho0h5.org'
    logging.info("HTTP 요청 시작...")
    
    ip = resolve_ip(domain)
    if ip is None:
        logging.error("IPv4 주소를 찾을 수 없어 요청 중단")
        return None

    url = f'https://{domain}/desk/call'
    headers = {
        'accept': 'application/json',
        'X-CSRFTOKEN': 'Epqb2YKaXPFjbgQwfCdzXci9Y0uUNxl8xNu534g9yjusk8i9w6FvRljWj1SJXY51',
        'Host': domain
    }

    try:
        logging.info(f"서버 {url}로 POST 요청 전송 중...")
        session = requests.Session()
        session.mount('https://', requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=1,
            pool_maxsize=1
        ))

        response = session.post(
            url,
            headers=headers,
            data='',
            timeout=10,
            verify=True
        )
        
        logging.info(f"서버 응답: {response.status_code}")
        logging.debug(f"응답 내용: {response.text}")
        
        if lcd:
            lcd.clear()
            lcd.write_string(f"Request sent\n{response.status_code}")
        
        buzzer = GPIO.PWM(37, 440)
        buzzer.start(50)
        time.sleep(0.5)
        buzzer.stop()
        
        return response

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP 요청 실패: {e}")
        if lcd:
            lcd.clear()
            lcd.write_string("Request failed")
        return None
    except Exception as e:
        logging.error(f"예기치 않은 오류: {e}")
        return None

def make_request_with_retry(max_retries=3, retry_delay=5):
    for attempt in range(max_retries):
        logging.info(f"요청 시도 {attempt + 1}/{max_retries}")
        response = make_request()
        if response is not None:
            logging.info("요청 성공")
            return response
            
        if attempt < max_retries - 1:
            logging.info(f"{retry_delay}초 후 재시도...")
            time.sleep(retry_delay)
    
    logging.error("최대 재시도 횟수 초과")
    return None


def check_study_time():
    try:
        response = requests.get('https://skycastle.cho0h5.org/chair/studytime', 
                                headers={'accept': 'application/json'})
        if response.status_code == 200:
            data = response.json()
            study_time_seconds = int(data['today_study_time_seconds'])  # float를 int로 변환
            hours, remainder = divmod(study_time_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            study_time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
            logging.info(f"오늘의 공부 시간: {study_time_str}")
            
            if lcd:
                lcd.clear()
                lcd.write_string(f"Study Time:\n{study_time_str}")
            
            return study_time_seconds
        else:
            logging.error(f"공부 시간 조회 실패: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"공부 시간 확인 중 오류 발생: {e}")
        return None
def check_warning():
    global lcd_reset_timer
    try:
        response = requests.get('https://skycastle.cho0h5.org/buzzer/status', 
                              headers={'accept': 'application/json'})
        if response.status_code == 200:
            data = response.json()
            warning_time = data['datetime']
            current_time = datetime.now()
            warning_datetime = datetime.strptime(warning_time, "%Y-%m-%d %H:%M:%S")
            
            # 서버 시간에 9시간 추가 (UTC to KST)
            warning_datetime = warning_datetime + timedelta(hours=9)
            
            time_diff = abs((current_time - warning_datetime).total_seconds())
            
            if time_diff <= 3:  # 3초 이내면
                buzzer = GPIO.PWM(37, 440)
                buzzer.start(50)
                time.sleep(1)
                buzzer.stop()
                logging.info("경고 감지: 부저 동작")
                if lcd:
                    lcd.clear()
                    lcd.write_string("Warning!\nReceived")
                
                # 기존 타이머가 있다면 취소
                if lcd_reset_timer:
                    lcd_reset_timer.cancel()
                
                # 5초 후에 LCD를 공부 시간 표시로 리셋하는 타이머 설정
                lcd_reset_timer = threading.Timer(5, reset_lcd_display)
                lcd_reset_timer.start()
            
            # 로그 출력
            logging.info(f"원본 경고 시간: {warning_time}")
            logging.info(f"조정된 경고 시간 (KST): {warning_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"현재 시간 (KST): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"시간 차이: {time_diff:.2f}초")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"경고 확인 중 네트워크 오류: {e}")
    except KeyError as e:
        logging.error(f"응답 데이터 형식 오류: {e}")
    except Exception as e:
        logging.error(f"경고 확인 중 오류 발생: {e}")

    
def main_loop():
    led_state = 0
    last_study_time_check = 0
    study_time_check_interval = 5  # 1분마다 공부 시간 확인
    logging.info("메인 루프 시작")
    
    while True:
        try:
            current_time = time.time()
            
            # 경고 상태 확인 (3초마다)
            check_warning()
             # 공부 시간 확인 (5초마다)
            if current_time - last_study_time_check >= study_time_check_interval and not lcd_reset_timer:
                check_study_time()
                last_study_time_check = current_time
            
            # 스위치 1 처리
            if not GPIO.input(11):
                led_state = (led_state + 1) % 4
                logging.info(f"스위치 1 눌림. LED 상태 변경: {led_state}")
                
                # 모든 LED 끄기
                for pin in led_pins:
                    GPIO.output(pin, GPIO.LOW)
                
                # 현재 상태에 따라 LED 켜기
                if led_state > 0:
                    GPIO.output(led_pins[led_state-1], GPIO.HIGH)
                    logging.info(f"LED {led_state} (Pin {led_pins[led_state-1]}) ON")
                else:
                    logging.info("모든 LED OFF")
                
                time.sleep(0.2)

            # 스위치 2 처리 (36번 핀)
            if not GPIO.input(36):
                logging.info("스위치 2 눌림. 관리자 호출 요청 전송")
                response = requests.post(
                    'https://skycastle.cho0h5.org/desk/call',
                    headers={
                        'accept': 'application/json',
                        'X-CSRFTOKEN': 'JYHIu3hZpKUkVzowCV7mF7Enhk9JxgEwCmLCv9NY0eJt4rQ9TpzizgFaClxyHHop'
                    },
                    data=''
                )
                
                if response.status_code == 200:
                    logging.info("관리자 호출 성공")
                    if lcd:
                        lcd.clear()
                        lcd.write_string("Call sent\nSuccess!")
                    # 호출 성공 알림음
                    buzzer = GPIO.PWM(37, 440)
                    buzzer.start(50)
                    time.sleep(0.5)
                    buzzer.stop()
                else:
                    logging.error(f"호출 실패: {response.status_code}")
                    if lcd:
                        lcd.clear()
                        lcd.write_string("Call failed!")
                
                time.sleep(0.2)

        except Exception as e:
            logging.error(f"메인 루프 에러: {e}")
            time.sleep(1)

def cleanup():
    global lcd_reset_timer
    logging.info("프로그램 정리 작업 시작")
    try:
        GPIO.cleanup()
        if lcd:
            lcd.clear()
        if lcd_reset_timer:
            lcd_reset_timer.cancel()
        logging.info("프로그램 정상 종료")
    except Exception as e:
        logging.error(f"cleanup 중 에러 발생: {e}")

if __name__ == "__main__":
    logging.info("프로그램 시작")
    while True:
        try:
            requests.packages.urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
            
            logging.info("하드웨어 초기화 시작")
            led_pins = setup_gpio()
            lcd = setup_lcd()
            buzzer = GPIO.PWM(37, 440)
            
            if lcd:
                lcd.clear()
                lcd.write_string("System Ready\nWaiting...")
            
            logging.info("초기화 완료, 메인 루프 시작")
            main_loop()
            
        except Exception as e:
            logging.error(f"치명적 에러 발생: {e}")
            cleanup()
            logging.info("5초 후 재시작...")
            time.sleep(5)
            continue
        
        finally:
            cleanup()
