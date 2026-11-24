"""찍은 사진들을 감열 프린터용 세로 스트립 한 장으로 합친다 (1컷이면 한 장짜리).

세로로 이어 붙이는 이유: 감열 프린터 용지는 폭이 고정(58mm)이고 길이는 자유라서,
포토부스의 '4컷 스트립' 형태가 용지에 그대로 맞는다.
사진 한 장씩 인쇄용 흑백 점 이미지로 바꾼 뒤(image_utils.to_printable) 흰 종이 위에 차례로 붙인다.
"""
import os
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config
from image_utils import to_printable

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "assets", "fonts", "PressStart2P-Regular.ttf")

MARGIN = 16          # 종이 가장자리 여백(점)
GAP = 12             # 사진 사이 간격
FOOTER = 64          # 아래쪽 글자 영역 높이
RATIO = (4, 3)       # 사진 한 칸의 가로:세로


def _font(px):
    try:
        return ImageFont.truetype(FONT_PATH, px)
    except OSError:
        return ImageFont.load_default(px)


def compose_strip(photos, width=None, stamp=None):
    """photos: PIL 이미지 목록(1장 또는 4장). 프린터 폭에 맞춘 1비트 이미지를 반환한다."""
    width = width or config.PRINT_WIDTH
    inner = width - 2 * MARGIN
    cell_h = inner * RATIO[1] // RATIO[0]
    n = len(photos)
    height = MARGIN + n * cell_h + (n - 1) * GAP + FOOTER
    paper = Image.new("1", (width, height), 1)                    # 1 = 흰색(인쇄 안 함)

    y = MARGIN
    for photo in photos:
        fitted = ImageOps.fit(photo.convert("RGB"), (inner, cell_h), Image.LANCZOS)   # 비율이 달라도 칸에 맞게 자름
        paper.paste(to_printable(fitted, inner), (MARGIN, y))
        y += cell_h + GAP

    d = ImageDraw.Draw(paper)
    top = height - FOOTER
    d.line((MARGIN, top + 6, width - MARGIN, top + 6), fill=0, width=2)
    d.text((MARGIN, top + 20), "PHOTOBOOTH", font=_font(16), fill=0)
    d.text((MARGIN, top + 44), stamp or time.strftime("%Y.%m.%d"), font=_font(8), fill=0)
    d.text((width - MARGIN, top + 44), f"{n} CUT", font=_font(8), fill=0, anchor="ra")
    return paper
