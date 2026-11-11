"""필터 이름 -> 이미지 처리 함수. 새 필터는 여기에 함수를 추가하고 FILTERS에 등록하면 된다.

감열 프린터는 흑백 점으로 찍으므로, 색이 아니라 '명암 차이'가 뚜렷한 필터 위주로 구성했다.
(피부 보정처럼 미세한 톤 변화는 인쇄물에서 거의 보이지 않아 제외)
"""
import cv2
import numpy as np
from PIL import Image, ImageOps

from face_sticker import FaceSticker


def basic(img, ctx):
    return img, ""


def contrast(img, ctx):
    """명암을 강하게: 어두운 곳은 더 어둡게, 밝은 곳은 더 밝게."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=10)
    return ImageOps.autocontrast(gray.point(lambda v: 255 * (v / 255) ** 1.6), cutoff=2).convert("RGB"), ""


def sketch(img, ctx):
    """연필 스케치: 흑백 반전 -> 흐리게 -> 원본을 나누기(color dodge)하면 윤곽선만 남는다."""
    gray = np.array(img.convert("L"))
    inverted_blur = cv2.GaussianBlur(255 - gray, (21, 21), 0)
    pencil = cv2.divide(gray, 255 - inverted_blur, scale=256)
    return Image.fromarray(pencil).convert("RGB"), ""


def cat(img, ctx):
    out, found = ctx["face"].apply_cat(img)
    return out, "" if found else "No face found"


FILTERS = {"basic": basic, "contrast": contrast, "sketch": sketch, "cat": cat}


class FilterBank:
    def __init__(self):
        self._ctx = {"face": FaceSticker()}

    def apply(self, name, pil_img):
        """(필터 적용된 이미지, 안내 메시지)를 반환."""
        return FILTERS.get(name, basic)(pil_img, self._ctx)
