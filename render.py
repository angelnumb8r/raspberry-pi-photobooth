"""화면에 그릴 한 장의 이미지를 만든다 (Tkinter/OpenCV 창과 분리된 순수 이미지 처리 코드).

구조: 화면 틀(배경, 프레임, 필터 목록 등)은 800x480 '기준 크기'에서 픽셀 단위로 그리고,
모니터 크기에 맞게 NEAREST(픽셀을 그대로 키우는 방식)로 확대한다 -> 어느 해상도에서도 픽셀 느낌이 선명하다.
카메라 사진만 확대된 위치에 따로 붙여서 사진은 부드럽게 보이게 한다.

레이어 순서: 틀(chrome) -> 사진(photo) -> 덮는 글자(overlay: 카운트다운 숫자 등)
"""
import math
import os
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config
from booth import State

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "assets", "fonts", "PressStart2P-Regular.ttf")   # SIL OFL 1.1 (같은 폴더의 OFL.txt)

BASE_W, BASE_H = 800, 480
PHOTO_BOX = (200, 84, 600, 384)          # 사진이 들어가는 칸 (400x300 = 카메라 4:3 비율)

# 색상 팔레트: 테마별로 한곳에 모았다. config.THEME = "christmas"(기본) 또는 "pastel"
PALETTES = {
    "christmas": dict(
        BG=(228, 215, 198),          # 채도 낮은 옅은 브라운(크래프트지 느낌)
        BG_DOT=(216, 201, 182),
        DARK=(74, 52, 44),           # 윤곽선·글자: 진한 브라운
        WHITE=(251, 246, 237),       # 따뜻한 크림색
        PAPER=(250, 246, 236),
        ACCENT=(122, 31, 46),        # 포인트: 버건디
        ACCENT_TEXT=(251, 246, 237),
        GOLD=(200, 164, 92),         # 절제된 골드
        SOFT=(196, 176, 150),        # 선택되지 않은 칸의 테두리
        SHADOW=(200, 182, 160),
        GREEN=(86, 112, 90),         # 소나무색 (장식에만 소량)
        PILL=(122, 31, 46),
        PILL_TEXT=(251, 246, 237),
        ERR=(184, 66, 52),
        ERR_TEXT=(251, 246, 237),
        CAM=(172, 138, 104),
        COUNT_STROKE=(122, 31, 46),
    ),
    "pastel": dict(
        BG=(207, 232, 243), BG_DOT=(190, 220, 235), DARK=(43, 58, 85), WHITE=(255, 255, 255),
        PAPER=(252, 250, 244), ACCENT=(244, 166, 184), ACCENT_TEXT=(43, 58, 85), GOLD=(249, 226, 125),
        SOFT=(142, 197, 232), SHADOW=(166, 205, 225), GREEN=(142, 197, 232), PILL=(249, 226, 125),
        PILL_TEXT=(43, 58, 85), ERR=(240, 128, 120), ERR_TEXT=(255, 255, 255), CAM=(142, 197, 232),
        COUNT_STROKE=(43, 58, 85),
    ),
}
THEME = getattr(config, "THEME", "christmas")
globals().update(PALETTES.get(THEME, PALETTES["christmas"]))

FILTER_ORDER = ["basic", "contrast", "cat", "sketch"]
FILTER_NAMES = {"basic": "BASIC", "contrast": "CONTRAST", "cat": "CAT", "sketch": "SKETCH"}

_fonts = {}


def _font(px):
    """픽셀 폰트는 8의 배수 크기에서 가장 선명하다. 폰트 파일이 없으면 기본 글꼴로 대체."""
    if px not in _fonts:
        try:
            _fonts[px] = ImageFont.truetype(FONT_PATH, px)
        except OSError:
            _fonts[px] = ImageFont.load_default(px)
    return _fonts[px]


# ---------------------------------------------------------------- 그림 도구
def _outline_poly(d, pts, fill):
    d.polygon(pts, fill=fill, outline=DARK, width=2)


def _star(d, cx, cy, r, fill=None):
    fill = GOLD if fill is None else fill
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    _outline_poly(d, pts, fill)


def _heart(d, cx, cy, s, fill=None):
    fill = ACCENT if fill is None else fill
    pts = []
    for i in range(48):
        t = 2 * math.pi * i / 48
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s / 16, cy + y * s / 16))
    _outline_poly(d, pts, fill)


def _flower(d, cx, cy, r):
    for i in range(5):
        a = -math.pi / 2 + i * 2 * math.pi / 5
        px, py = cx + r * 0.85 * math.cos(a), cy + r * 0.85 * math.sin(a)
        d.ellipse((px - r * 0.55, py - r * 0.55, px + r * 0.55, py + r * 0.55), fill=ACCENT, outline=DARK, width=2)
    d.ellipse((cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4), fill=GOLD, outline=DARK, width=2)


def _sparkle(d, cx, cy, r, fill=None):
    fill = WHITE if fill is None else fill
    pts = []
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.28
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    _outline_poly(d, pts, fill)


def _bow(d, cx, cy, s, fill=None):
    fill = ACCENT if fill is None else fill
    _outline_poly(d, [(cx, cy), (cx - s, cy - s * 0.65), (cx - s, cy + s * 0.65)], fill)
    _outline_poly(d, [(cx, cy), (cx + s, cy - s * 0.65), (cx + s, cy + s * 0.65)], fill)
    d.ellipse((cx - s * 0.25, cy - s * 0.25, cx + s * 0.25, cy + s * 0.25), fill=fill, outline=DARK, width=2)


def _camera_icon(d, x, y):
    d.rectangle((x + 8, y, x + 22, y + 6), fill=DARK)                                   # 윗부분
    d.rounded_rectangle((x, y + 5, x + 32, y + 28), radius=4, fill=CAM, outline=DARK, width=3)
    d.ellipse((x + 8, y + 9, x + 24, y + 25), fill=WHITE, outline=DARK, width=3)       # 렌즈 바깥
    d.ellipse((x + 12, y + 13, x + 20, y + 21), fill=DARK)                              # 렌즈 안쪽
    d.rectangle((x + 25, y + 9, x + 28, y + 11), fill=GOLD)                           # 플래시


def _leaf(d, cx, cy, length, width, angle, fill):
    """잎 모양(양 끝이 뾰족한 렌즈 모양)을 angle 방향으로 그린다."""
    pts = []
    n = 10
    for i in range(n + 1):                      # 한쪽 곡선
        u = i / n
        pts.append((u * length, math.sin(math.pi * u) * width / 2))
    for i in range(n, -1, -1):                  # 반대쪽 곡선
        u = i / n
        pts.append((u * length, -math.sin(math.pi * u) * width / 2))
    c, sn = math.cos(angle), math.sin(angle)
    pts = [(cx + x * c - y * sn, cy + x * sn + y * c) for x, y in pts]
    _outline_poly(d, pts, fill)


def _tree(d, cx, cy, h):
    """소나무: 삼각형 3단 + 줄기 + 꼭대기 별 + 장식 구슬."""
    w = h * 0.5
    d.rectangle((cx - w * 0.12, cy + h * 0.38, cx + w * 0.12, cy + h * 0.5), fill=DARK)
    for apex, base, half in ((-0.40, -0.02, 0.30), (-0.22, 0.20, 0.42), (-0.02, 0.40, 0.55)):
        _outline_poly(d, [(cx, cy + h * apex), (cx + w * half * 1.0, cy + h * base), (cx - w * half * 1.0, cy + h * base)], GREEN)
    _star(d, cx, cy - h * 0.46, h * 0.13, GOLD)
    for ox, oy, col in ((-0.15, 0.12, ACCENT), (0.18, 0.28, GOLD), (-0.05, 0.30, GOLD), (0.08, 0.04, ACCENT)):
        d.ellipse((cx + w * ox - 3, cy + h * oy - 3, cx + w * ox + 3, cy + h * oy + 3), fill=col)


def _gift(d, cx, cy, s):
    """선물 상자: 버건디 상자 + 크림색 리본."""
    x0, x1, y0, y1 = cx - s / 2, cx + s / 2, cy - s * 0.15, cy + s * 0.5
    d.rectangle((x0, y0, x1, y1), fill=ACCENT, outline=DARK, width=2)
    d.rectangle((x0 - 3, y0 - s * 0.18, x1 + 3, y0), fill=ACCENT, outline=DARK, width=2)
    d.rectangle((cx - s * 0.09, y0 - s * 0.18, cx + s * 0.09, y1), fill=WHITE, outline=DARK, width=1)
    for sign in (-1, 1):
        d.ellipse((cx + sign * s * 0.2 - s * 0.16, y0 - s * 0.4, cx + sign * s * 0.2 + s * 0.16, y0 - s * 0.14), fill=WHITE, outline=DARK, width=2)


def _snowflake(d, cx, cy, r):
    """눈송이: 6방향 선 (크림색 선 아래에 갈색 선을 깔아 윤곽선 효과)."""
    for width, color in ((5, DARK), (2, WHITE)):
        for i in range(3):
            a = i * math.pi / 3
            dx, dy = r * math.cos(a), r * math.sin(a)
            d.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=color, width=width)
        if width == 2:
            continue
    for i in range(6):                                   # 가지 끝의 작은 점
        a = i * math.pi / 3
        px, py = cx + r * 0.62 * math.cos(a), cy + r * 0.62 * math.sin(a)
        d.ellipse((px - 2, py - 2, px + 2, py + 2), fill=WHITE, outline=DARK, width=1)


def _holly(d, cx, cy, s):
    """호랑가시나무: 초록 잎 두 장 + 버건디 열매 세 개."""
    _leaf(d, cx, cy, s, s * 0.55, math.radians(200), GREEN)
    _leaf(d, cx, cy, s, s * 0.55, math.radians(-20), GREEN)
    for ox, oy in ((-0.17, 0.02), (0.17, 0.02), (0.0, 0.2)):
        px, py = cx + s * ox, cy + s * oy
        d.ellipse((px - s * 0.16, py - s * 0.16, px + s * 0.16, py + s * 0.16), fill=ACCENT, outline=DARK, width=2)
        d.rectangle((px - 2, py - 3, px - 1, py - 2), fill=WHITE)


def _bell(d, cx, cy, s):
    """종: 좌우 대칭 옆모습 + 방울."""
    half = [(0.0, -0.55), (0.14, -0.52), (0.27, -0.42), (0.34, -0.25), (0.37, -0.02), (0.42, 0.18), (0.58, 0.34)]
    pts = [(cx + x * s, cy + y * s) for x, y in half] + [(cx - x * s, cy + y * s) for x, y in reversed(half)]
    _outline_poly(d, pts, GOLD)
    d.line((cx - 0.58 * s, cy + 0.34 * s, cx + 0.58 * s, cy + 0.34 * s), fill=DARK, width=2)
    d.ellipse((cx - s * 0.1, cy + s * 0.36, cx + s * 0.1, cy + s * 0.56), fill=GOLD, outline=DARK, width=2)
    d.ellipse((cx - s * 0.07, cy - s * 0.66, cx + s * 0.07, cy - s * 0.52), fill=ACCENT, outline=DARK, width=2)


def _tape(w=64, h=18, angle=35):
    """마스킹 테이프 모양 (분홍 바탕에 흰 점선). 회전해서 프레임 모서리에 붙인다."""
    t = Image.new("RGBA", (w, h), ACCENT + (255,))
    td = ImageDraw.Draw(t)
    for x in range(4, w, 10):
        td.rectangle((x, h // 2 - 1, x + 3, h // 2 + 1), fill=WHITE)
    td.rectangle((0, 0, w - 1, h - 1), outline=DARK, width=2)
    return t.rotate(angle, expand=True, resample=Image.NEAREST)


def _shadow_box(d, box, radius=8, offset=6):
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 + offset, y0 + offset, x1 + offset, y1 + offset), radius=radius, fill=SHADOW)


def _background():
    img = Image.new("RGB", (BASE_W, BASE_H), BG)
    d = ImageDraw.Draw(img)
    for y in range(8, BASE_H, 24):
        for x in range(8, BASE_W, 24):
            d.rectangle((x, y, x + 1, y + 1), fill=BG_DOT)
    if THEME == "christmas":                               # 눈 내리는 느낌: 고정된 위치에 작은 십자 눈송이
        seed = 7
        for _ in range(34):
            seed = (seed * 1103515245 + 12345) % (2 ** 31)
            x = 6 + seed % (BASE_W - 12)
            seed = (seed * 1103515245 + 12345) % (2 ** 31)
            y = 60 + seed % (BASE_H - 66)
            d.rectangle((x - 1, y, x + 1, y), fill=WHITE)
            d.rectangle((x, y - 1, x, y + 1), fill=WHITE)
    return img


# ---------------------------------------------------------------- 화면 구성
def _hint_for(filter_name):
    """config.FILTER_BY_FINGERS를 뒤집어서 '어떤 손 모양이 이 필터인지' 글자로 만든다."""
    counts = sorted(n for n, f in config.FILTER_BY_FINGERS.items() if f == filter_name)
    words = []
    for n in counts:
        words.append("FIST" if n == 0 else "PALM" if n == 4 else f"{n} FINGER" + ("S" if n > 1 else ""))
    return " / ".join(words)


def _draw_title(d):
    d.rectangle((0, 0, BASE_W, 50), fill=WHITE)
    d.rectangle((0, 50, BASE_W, 53), fill=DARK)
    _camera_icon(d, 20, 11)
    d.text((66, 26), "PHOTOBOOTH", font=_font(24), fill=DARK, anchor="lm")
    _title_deco(d)


def _title_deco(d):
    if THEME == "christmas":
        _snowflake(d, 722, 26, 11)
        _snowflake(d, 756, 18, 6)
    else:
        _sparkle(d, 720, 26, 10, GOLD)
        _sparkle(d, 752, 20, 6, ACCENT)


def _draw_doodles(d):
    if THEME == "christmas":
        _star(d, 58, 108, 20, GOLD)
        _tree(d, 128, 190, 98)
        _gift(d, 62, 276, 46)
        _snowflake(d, 140, 346, 17)
        _holly(d, 62, 402, 38)
        _snowflake(d, 664, 398, 14)
        _bell(d, 732, 392, 40)
    else:
        _star(d, 60, 118, 18)
        _heart(d, 130, 186, 30)
        _flower(d, 62, 262, 17)
        _sparkle(d, 140, 330, 14, WHITE)
        _bow(d, 70, 396, 20)
        _sparkle(d, 664, 398, 12, WHITE)
        _heart(d, 732, 396, 22, ACCENT)


def _draw_photo_frame(d, chrome, state):
    x0, y0, x1, y1 = PHOTO_BOX
    if state in (State.RESULT, State.PRINTING):
        # 인쇄될 영수증 종이 모양: 아래쪽이 톱니 모양
        px0, px1, py0, pb = x0 - 14, x1 + 14, y0 - 14, y1 + 22
        teeth = []
        x = px1
        while x - 8 >= px0:
            teeth += [(x, pb), (x - 8, pb + 8)]
            x -= 16
        teeth.append((px0, pb))
        outline = [(px0, py0), (px1, py0)] + teeth
        d.polygon([(a + 6, b + 6) for a, b in outline], fill=SHADOW)
        d.polygon(outline, fill=PAPER, outline=DARK, width=3)
    else:
        outer = (x0 - 8, y0 - 8, x1 + 8, y1 + 8)
        _shadow_box(d, outer)
        d.rounded_rectangle(outer, radius=8, fill=WHITE, outline=DARK, width=3)
        for (cx, cy, ang) in ((outer[0] + 6, outer[1] + 6, 40), (outer[2] - 6, outer[3] - 6, 40)):
            t = _tape(angle=ang)
            chrome.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)), t)
    d.rectangle(PHOTO_BOX, fill=DARK)


def _draw_filters(d, active):
    d.text((632, 70), "FILTER", font=_font(16), fill=DARK, anchor="lm")
    y = 92
    for name in FILTER_ORDER:
        box = (632, y, 788, y + 58)
        is_on = name == active
        if is_on:
            d.polygon([(612, y + 29 - 8), (612, y + 29 + 8), (624, y + 29)], fill=DARK)
        d.rounded_rectangle(box, radius=6, fill=ACCENT if is_on else WHITE, outline=DARK if is_on else SOFT, width=3)
        d.text((box[0] + 12, y + 20), FILTER_NAMES[name], font=_font(16), fill=ACCENT_TEXT if is_on else DARK, anchor="lm")
        d.text((box[0] + 12, y + 42), _hint_for(name), font=_font(8), fill=ACCENT_TEXT if is_on else DARK, anchor="lm")
        y += 66


def _draw_pill(d, text, fill=None, color=None, blink_arrow=None):
    fill = PILL if fill is None else fill
    color = PILL_TEXT if color is None else color
    f = _font(16)
    w = int(d.textlength(text, font=f)) + (84 if blink_arrow else 56)
    x0 = (BASE_W - w) // 2
    box = (x0, 424, x0 + w, 462)
    d.rounded_rectangle((box[0] + 4, box[1] + 4, box[2] + 4, box[3] + 4), radius=10, fill=SHADOW)
    d.rounded_rectangle(box, radius=10, fill=fill, outline=DARK, width=3)
    d.text((BASE_W // 2 + (10 if blink_arrow else 0), 444), text, font=f, fill=color, anchor="mm")
    if blink_arrow:
        d.polygon([(box[0] + 16, 444 - 7), (box[0] + 16, 444 + 7), (box[0] + 26, 444)], fill=color)


def _layers(frame, t):
    """(틀 이미지, 덮는 글자 이미지, 사진, 사진이 들어갈 칸)을 만든다."""
    chrome = _background()
    d = ImageDraw.Draw(chrome)
    _draw_title(d)
    _draw_doodles(d)
    _draw_photo_frame(d, chrome, frame.state)
    d = ImageDraw.Draw(chrome)
    _draw_filters(d, frame.filter_name)

    overlay = Image.new("RGBA", (BASE_W, BASE_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    if frame.notice:
        text = frame.notice if len(frame.notice) <= 42 else frame.notice[:41] + "~"
        _draw_pill(d, text, fill=ERR, color=ERR_TEXT)
    elif frame.state is State.IDLE:
        _draw_pill(d, "PRESS THE BUTTON", blink_arrow=int(t * 2) % 2 == 0 or None)
    elif frame.state is State.COUNTDOWN:
        _draw_pill(d, "SMILE!")
    elif frame.state is State.RESULT:
        _draw_pill(d, "NICE SHOT!")
    else:
        _draw_pill(d, "PRINTING" + ("." * (int(t * 3) % 4)).ljust(3))

    cx = (PHOTO_BOX[0] + PHOTO_BOX[2]) // 2
    cy = (PHOTO_BOX[1] + PHOTO_BOX[3]) // 2
    if frame.big_text:
        od.text((cx, cy), frame.big_text, font=_font(96), fill=WHITE, anchor="mm", stroke_width=6, stroke_fill=COUNT_STROKE)
    if frame.image is None:
        od.text((cx, cy), "NO CAMERA", font=_font(24), fill=WHITE, anchor="mm")
    return chrome, overlay, frame.image


def render(frame, size, t=None):
    """booth.Frame -> 화면 크기(size)에 맞춘 PIL 이미지. t는 깜빡임/점 애니메이션용 시간(초)."""
    t = time.monotonic() if t is None else t
    w, h = size
    chrome, overlay, photo = _layers(frame, t)

    scale = min(w / BASE_W, h / BASE_H)
    tw, th = max(1, int(BASE_W * scale)), max(1, int(BASE_H * scale))
    ox, oy = (w - tw) // 2, (h - th) // 2
    canvas = Image.new("RGB", (w, h), BG)
    # 화면 비율이 달라 좌우/상하에 여백이 생겨도 제목 띠는 끝까지 이어지게 먼저 칠해 둔다
    cd = ImageDraw.Draw(canvas)
    cd.rectangle((0, 0, w, oy + int(50 * scale)), fill=WHITE)
    cd.rectangle((0, oy + int(50 * scale), w, oy + int(53 * scale)), fill=DARK)
    canvas.paste(chrome.resize((tw, th), Image.NEAREST), (ox, oy))

    if photo is not None:
        bx0, by0, bx1, by1 = PHOTO_BOX
        box = (ox + int(bx0 * scale), oy + int(by0 * scale), ox + int(bx1 * scale), oy + int(by1 * scale))
        bw, bh = box[2] - box[0], box[3] - box[1]
        is_print = frame.state in (State.RESULT, State.PRINTING)
        fitted = ImageOps.contain(photo.convert("RGB"), (bw, bh), Image.NEAREST if is_print else Image.BILINEAR)
        canvas.paste(fitted, (box[0] + (bw - fitted.width) // 2, box[1] + (bh - fitted.height) // 2))

    ov = overlay.resize((tw, th), Image.NEAREST)
    canvas.paste(ov, (ox, oy), ov)
    return canvas
