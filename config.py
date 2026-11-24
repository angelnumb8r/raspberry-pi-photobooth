"""모든 설정값을 한 곳에 모아 둔다.

왜 따로 빼는가: Mac(개발용)과 라즈베리파이(실물)는 카메라 번호, 프린터 ID, 화면 해상도가 다르다.
설정이 코드 곳곳에 흩어져 있으면 이전할 때 여기저기 고쳐야 하지만,
여기만 바꾸면 되도록 하면 이전 작업이 한 파일 수정으로 끝난다.
"""

# ---- 카메라 ----
CAMERA_INDEX = 0                 # 라즈베리파이: `ls /dev/video*`로 확인한 번호
CAMERA_SIZE = (640, 480)         # 촬영/미리보기 해상도 (느리면 (320, 240)으로)
FAKE_CAMERA_IMAGE = None         # 카메라 없이 개발할 때 사진 경로 지정 (예: "tests/sample.jpg")
MIRROR_PREVIEW = True            # 화면에서만 좌우 반전(거울처럼). 인쇄물은 반전하지 않음

# ---- 손 인식 ----
HAND_MODEL_PATH = "models/hand_landmarker.task"   # README의 다운로드 명령 참고
DETECT_SIZE = (320, 240)         # 인식용 축소 해상도. 작을수록 빠름
DETECT_EVERY_N_FRAMES = 3        # 매 프레임이 아니라 N프레임마다 인식 (CPU 절약)
GESTURE_STABLE_FRAMES = 4        # 같은 결과가 이만큼 연속될 때만 필터 변경 (오인식 방지)

# 펴진 손가락 개수(엄지 제외) -> 필터 이름
FILTER_BY_FINGERS = {
    0: "basic",      # 주먹 / 손 없음
    1: "contrast",   # 검지
    2: "cat",        # V 사인
    3: "sketch",     # 세 손가락
    4: "basic",      # 손바닥
}
FILTER_LABELS = {"basic": "BASIC", "contrast": "HIGH CONTRAST", "cat": "CAT", "sketch": "SKETCH"}

# ---- 동작 흐름 ----
COUNTDOWN_SECONDS = 3
DEFAULT_MODE = 4                 # SPACE(또는 물리 버튼)로 넘어갈 때 쓰는 기본 모드: 1(1컷) 또는 4(4컷)
FLASH_SECONDS = 0.12             # 촬영 순간 화면이 하얗게 번쩍이는 시간
INTERVAL_SECONDS = 1.2           # 4컷에서 한 장 찍은 뒤 다음 카운트다운까지 쉬는 시간(찍힌 사진을 보여 줌)
DONE_SECONDS = 10                # 인쇄가 끝난 뒤 초기 화면으로 돌아가기까지의 시간

# ---- 프린터 ----
PRINT_WIDTH = 384                # 58mm 감열 프린터의 가로 점 수(모델에 따라 다름, 사양서 확인)
PRINTER_USB_IDS = None           # 실물: (vendor_id, product_id). `lsusb`로 확인. None이면 가상 프린터
OUTPUT_DIR = "output"            # 가상 프린터가 인쇄용 이미지를 저장하는 폴더

# ---- 버튼 ----
GPIO_BUTTON_PIN = 17             # BCM 번호
BUTTON_PULL_UP = False           # 눌렀을 때 값이 반대로 나오면 True/False를 바꿔 본다

# ---- 화면 테마 ----
THEME = "mono"                   # "mono"(블랙·차콜·실버) / "christmas"(브라운+버건디) / "pastel"(하늘색+분홍)

# ---- 이 기기만의 설정 (저장소에 올리지 않는 config_local.py) ----
# 카메라 방향, 프린터 ID처럼 기기마다 다른 값은 config_local.py에 적는다. 파일이 없으면 무시된다.
# 예) RPICAM_EXTRA_ARGS = ["--rotation", "180"]   # CSI 카메라가 거꾸로 달려 있을 때
try:
    from config_local import *   # noqa: F401,F403
except ImportError:
    pass
