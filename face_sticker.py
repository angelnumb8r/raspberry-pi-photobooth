"""얼굴 위치를 찾아 고양이 스티커(귀/코/수염)를 얹는다.

얼굴 찾기는 OpenCV에 포함된 Haar Cascade를 쓴다.
- 장점: 별도 모델 파일이 필요 없고 라즈베리파이에서 가벼움
- 한계: 얼굴 '네모 상자'만 알려 줌(눈/코 좌표 없음), 정면 얼굴 위주, 기울어진 얼굴은 스티커가 같이 기울지 않음
  -> 더 정밀하게 하려면 MediaPipe Face Landmarker로 교체 (이 파일의 apply_cat만 바꾸면 됨)
"""
import os

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CASCADE = "haarcascade_frontalface_default.xml"


def _find_cascade():
    candidates = []
    if hasattr(cv2, "data"):
        candidates.append(os.path.join(cv2.data.haarcascades, CASCADE))
    candidates += [f"/usr/share/opencv4/haarcascades/{CASCADE}", f"/usr/share/opencv/haarcascades/{CASCADE}"]
    return next((p for p in candidates if os.path.exists(p)), None)


class FaceSticker:
    def __init__(self):
        path = _find_cascade()
        self._cascade = cv2.CascadeClassifier(path) if path else None
        load = lambda n: Image.open(os.path.join(HERE, "assets", n)).convert("RGBA")
        self._ears, self._nose, self._whiskers = load("cat_ears.png"), load("cat_nose.png"), load("cat_whiskers.png")

    def detect_face(self, pil_img):
        """가장 큰 얼굴의 (x, y, w, h)를 반환. 없으면 None."""
        if self._cascade is None:
            return None
        gray = np.array(pil_img.convert("L"))
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        return tuple(max(faces, key=lambda f: f[2] * f[3]))

    @staticmethod
    def _paste(base, sticker, width, cx, cy):
        """스티커를 가로 width로 줄여 (cx, cy)가 중심이 되게 붙인다."""
        h = int(sticker.height * width / sticker.width)
        s = sticker.resize((int(width), h), Image.LANCZOS)
        base.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2)))

    def apply_cat(self, pil_img):
        """(스티커 적용된 이미지, 얼굴을 찾았는지)를 반환."""
        face = self.detect_face(pil_img)
        if face is None:
            return pil_img, False
        x, y, w, h = [int(v) for v in face]
        out = pil_img.convert("RGBA")
        cx = x + w / 2
        # 비율은 정면 얼굴 기준 경험값: 귀는 이마 위, 코는 얼굴 상자의 약 62% 높이
        self._paste(out, self._ears, w * 1.55, cx, y + 0.16 * h - self._ears.height * (w * 1.55 / self._ears.width) / 2)
        self._paste(out, self._whiskers, w * 1.45, cx, y + 0.68 * h)
        self._paste(out, self._nose, w * 0.26, cx, y + 0.62 * h)
        return out.convert("RGB"), True
