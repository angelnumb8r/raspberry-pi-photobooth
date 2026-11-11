# 라즈베리파이 포토부스

버튼(또는 SPACE)을 누르면 카운트다운 후 촬영하고, 손가락 개수로 고른 필터를 적용해 감열 프린터로 인쇄한다.
카메라·버튼·프린터가 없어도 가상 장치로 동작하므로 Mac에서 먼저 개발하고, 부품이 도착하면 설정만 바꿔 이전한다.

## 필터 (손가락 개수, 엄지 제외)

| 손 모양 | 필터 | 설명 |
|---|---|---|
| 주먹 / 손바닥 / 손 없음 | basic | 기본 |
| 검지 1개 | contrast | 명암을 강하게 (인쇄에서 선명) |
| V 사인(2개) | cat | 얼굴에 고양이 귀·코·수염 스티커 |
| 3개 | sketch | 연필 스케치 |

## 설치 (Mac 개발 환경 / 라즈베리파이 공통)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- `requirements.txt`의 `opencv-python<5`는 의도한 설정이다. OpenCV 5.x에는 얼굴 검출 파일(Haar)이 빠져 있어서 4.x를 쓴다.
- Mac에서 `gpiozero`·`pyusb` 설치가 문제되면 해당 줄만 빼고 설치해도 된다 (버튼·프린터가 가상 장치로 대체됨).

## 손 인식 모델 내려받기 (1회)

```bash
mkdir -p models
curl -L -o models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
```

모델이 없으면 손 인식만 꺼지고(필터는 basic 고정) 나머지는 정상 동작한다.
최신 MediaPipe에서는 예전 `mp.solutions` API가 없어서 Tasks API(`HandLandmarker`)를 쓴다.

## 실행

```bash
python main.py --windowed     # 창 모드 (개발용)
python main.py                # 전체화면 (라즈베리파이)
```

SPACE = 버튼 대신 촬영 시작, ESC = 종료.
시작할 때 터미널에 어떤 장치가 실물이고 어떤 것이 가상인지 출력된다.
카메라가 없을 때 사진으로 개발하려면 `config.py`의 `FAKE_CAMERA_IMAGE = "tests/sample.jpg"`로 지정한다.

## 하드웨어 없이 검증

```bash
python tests/test_pipeline.py
```

손가락 개수 판별, 필터 4종, 가상 프린터 출력, 상태 머신(카운트다운·중복 입력 무시·프린터 오류 복구)을 확인한다.

## 부품 도착 후 바꿀 것 (config.py)

| 항목 | 확인 방법 | 설정 |
|---|---|---|
| 카메라 번호 | `ls /dev/video*` | `CAMERA_INDEX` |
| 프린터 USB ID | `lsusb` (예: `ID 0416:5011`) | `PRINTER_USB_IDS = (0x0416, 0x5011)` |
| 프린터 폭 | 프린터 사양서 | `PRINT_WIDTH` (58mm는 보통 384) |
| 버튼 핀 | 배선한 GPIO 번호 | `GPIO_BUTTON_PIN` |
| 버튼 극성 | 눌렀을 때 반응이 없거나 반대면 | `BUTTON_PULL_UP`을 True/False로 바꿈 |
| 미리보기가 끊김 | - | `CAMERA_SIZE`, `DETECT_SIZE`, `DETECT_EVERY_N_FRAMES` 조정 |

주의:
- 프린터는 일반 사용자 권한으로 USB 접근이 거부될 수 있다 (udev 규칙 추가 또는 `sudo` 실행으로 원인 구분).
- 버튼 모듈(KY-004)의 전원은 GPIO 보호를 위해 5V가 아니라 3.3V에 연결한다.
- 프린터는 자체 전원 어댑터를 쓰고, 라즈베리파이 전원과 분리한다.

## 화면(UI)

화면은 5개다: 대기(미리보기 + 필터 목록), 카운트다운, 결과(실제 인쇄될 흑백 이미지), 인쇄 중, 오류 안내.

- 800x480 기준 크기에서 픽셀 단위로 그린 뒤 모니터 크기에 맞게 확대한다 (사진만 부드럽게 따로 붙임)
- 테마: `config.py`의 `THEME`으로 고른다. `christmas`(옅은 브라운 + 버건디 포인트, 트리·선물·눈송이 등) / `pastel`(하늘색 + 분홍)
- 색상은 `render.py`의 `PALETTES`, 장식은 `_draw_doodles`, 필터 이름은 `FILTER_NAMES`에서 바꾼다
- 글꼴: Press Start 2P (SIL Open Font License 1.1, `assets/fonts/OFL.txt`). 파일이 없으면 기본 글꼴로 대체됨
- 화면 미리보기: `docs/ui_preview.png`

## 파일 구조

| 파일 | 역할 | 이전 시 |
|---|---|---|
| `main.py` | 화면(Tkinter) 실행 | 그대로 |
| `booth.py` | 동작 순서(상태 머신) | 그대로 |
| `render.py` | 화면 이미지 그리기 | 그대로 |
| `camera.py` `button.py` `printer.py` | 장치 접근 | 실물 설정 확인 |
| `hand_gesture.py` | 손 인식 + 손가락 개수 판별 | 그대로 |
| `filters.py` `face_sticker.py` `image_utils.py` | 필터·스티커·인쇄 변환 | 그대로 |
| `config.py` | 모든 설정 | 값만 수정 |
| `make_stickers.py` | 스티커 PNG 생성 | 디자인 바꿀 때 |

구성도·흐름도는 `docs/`에 있다.

## 검증 상태

- Mac/리눅스(가상 장치)에서 `tests/test_pipeline.py` 전체 통과
- 실제 라즈베리파이, USB 카메라, 버튼, 프린터, MediaPipe 손 인식 모델은 아직 검증하지 못했다 (부품·모델 파일 필요)
- 프레임 속도 등 성능은 실물에서 측정해야 한다

## 한계와 개선 방향

- 얼굴 검출이 Haar Cascade라 정면 얼굴 위주이고, 기울어진 얼굴에는 스티커가 같이 기울지 않는다 → MediaPipe Face Detector/Landmarker로 교체하면 눈·코 좌표를 쓸 수 있다
- 엄지는 오판이 잦아 세지 않는다. 엄지까지 쓰려면 별도 규칙이 필요하다
- 화면 글자는 한글 폰트 문제를 피하려고 영어로 표시한다
