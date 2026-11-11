"""카메라 입력. USB 웹캠(UVC)은 OpenCV로 읽는다.

OV9726은 라즈베리파이 CSI 슬롯용 카메라가 아니라 USB 웹캠이라 picamera 대신 OpenCV를 쓴다.
카메라가 없거나 열리지 않으면 FAKE_CAMERA_IMAGE(사진 파일) 또는 단색 화면으로 대체해서
카메라 없이도 화면/필터/인쇄 흐름을 개발할 수 있게 한다.
"""
import cv2
import numpy as np

import config


class Camera:
    def __init__(self, index=config.CAMERA_INDEX, size=config.CAMERA_SIZE):
        self.size = size
        self._fake = None
        self._cap = None
        if config.FAKE_CAMERA_IMAGE:
            img = cv2.imread(config.FAKE_CAMERA_IMAGE)
            if img is not None:
                self._fake = cv2.resize(img, size)
        if self._fake is None:
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
                self._cap = cap
        self.is_real = self._cap is not None

    def read(self):
        """BGR 프레임 1장을 반환한다. 실패하면 None."""
        if self._cap is not None:
            ok, frame = self._cap.read()
            return frame if ok else None
        if self._fake is not None:
            return self._fake.copy()
        return np.full((self.size[1], self.size[0], 3), 90, np.uint8)  # 카메라 없음: 회색 화면

    def close(self):
        if self._cap is not None:
            self._cap.release()
