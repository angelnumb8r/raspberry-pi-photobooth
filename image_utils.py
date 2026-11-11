"""화면/촬영용 이미지를 감열 프린터용 이미지로 바꾼다.

감열 프린터는 '검정 점이 있다/없다' 두 가지만 표현한다(1비트).
회색을 점의 밀도로 흉내 내는 것이 디더링(여기서는 PIL 기본인 Floyd-Steinberg)이다.
인쇄 직전에 한 번만 변환해서 화면에는 원본에 가까운 이미지를 보여 준다.
"""
import cv2
from PIL import Image, ImageOps

import config


def bgr_to_pil(frame_bgr):
    return Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))


def to_printable(img, width=config.PRINT_WIDTH):
    """PIL 이미지를 프린터 폭에 맞춘 1비트(흑백 점) 이미지로 변환한다."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=2)   # 명암 범위를 넓혀 인쇄가 흐려지지 않게 함
    ratio = width / gray.width
    gray = gray.resize((width, int(gray.height * ratio)), Image.LANCZOS)
    return gray.convert("1")                                    # 디더링으로 1비트 변환
