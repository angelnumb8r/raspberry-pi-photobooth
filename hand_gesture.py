"""손가락 개수 인식 (MediaPipe Hand Landmarker + 직접 만든 판별 규칙).

MediaPipe가 해 주는 일: 손 위치를 찾고 21개 관절 좌표(랜드마크)를 알려 준다.
이 파일에서 직접 하는 일: 좌표로 '펴진 손가락이 몇 개인지' 판단한다 (count_fingers).

판별 규칙: 손목에서 '손가락 끝'까지의 거리가 '두 번째 마디(PIP)'까지의 거리보다 충분히 멀면 펴진 것.
- 위/아래 방향을 비교하지 않고 거리로 비교하므로 손이 기울어져도 동작함
- 엄지는 굽는 방향이 달라 오판이 잦아서 제외하고 네 손가락(검지~새끼)만 센다 -> 결과는 0~4
"""
import math
from collections import deque

import cv2

import config

# (손가락 끝 번호, PIP 마디 번호)  -- MediaPipe 손 랜드마크 번호
FINGER_JOINTS = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "pinky": (20, 18)}
WRIST = 0
EXTENDED_RATIO = 1.2   # 끝까지 거리 / PIP까지 거리가 이 값보다 크면 '펴짐'


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def count_fingers(landmarks):
    """landmarks: .x/.y 값을 가진 21개 점. 펴진 손가락 수(엄지 제외, 0~4)를 반환."""
    wrist = landmarks[WRIST]
    count = 0
    for tip, pip in FINGER_JOINTS.values():
        if _dist(landmarks[tip], wrist) > _dist(landmarks[pip], wrist) * EXTENDED_RATIO:
            count += 1
    return count


class Stabilizer:
    """같은 값이 n번 연속 들어올 때만 값을 바꾼다 (한 프레임짜리 오인식 무시)."""

    def __init__(self, n=config.GESTURE_STABLE_FRAMES, initial=None):
        self._buf = deque(maxlen=n)
        self.value = initial

    def update(self, x):
        self._buf.append(x)
        if len(self._buf) == self._buf.maxlen and len(set(self._buf)) == 1:
            self.value = x
        return self.value


class HandGesture:
    def __init__(self, model_path=config.HAND_MODEL_PATH):
        self.available = False
        self.error = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1,
            )
            self._mp = mp
            self._detector = vision.HandLandmarker.create_from_options(options)
            self.available = True
        except Exception as e:  # 모델 파일 없음, mediapipe 미설치 등 -> 손 인식만 꺼지고 나머지는 동작
            self.error = str(e)

    def detect(self, frame_bgr):
        """프레임에서 펴진 손가락 수를 반환. 손이 없으면 0, 인식 기능이 꺼져 있으면 None."""
        if not self.available:
            return None
        small = cv2.resize(frame_bgr, config.DETECT_SIZE)   # 작게 줄여서 인식 -> 라즈베리파이에서 속도 확보
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(image)
        if not result.hand_landmarks:
            return 0
        return count_fingers(result.hand_landmarks[0])
