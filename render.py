"""화면에 그릴 한 장의 이미지를 만든다 (Tkinter와 분리해 둔 순수 이미지 처리 코드).

화면 구성만 따로 두면 모니터/디스플레이 없이도 결과를 이미지 파일로 저장해 확인할 수 있다.
글자는 영어만 쓴다: 라즈베리파이 기본 폰트에는 한글이 없을 수 있기 때문이다.
"""
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size):
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render(frame, size):
    """booth.Frame -> 화면 크기(size)에 맞춘 PIL 이미지."""
    w, h = size
    canvas = Image.new("RGB", (w, h), (20, 20, 20))
    if frame.image is not None:
        img = frame.image.copy()
        img.thumbnail((w, h))
        canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    d = ImageDraw.Draw(canvas)
    if frame.filter_label:
        d.text((16, 12), f"FILTER: {frame.filter_label}", font=_font(max(18, h // 22)), fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    if frame.big_text:
        d.text((w // 2, h // 2), frame.big_text, font=_font(h // 3), fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
    text = frame.notice or frame.hint
    if text:
        d.text((w // 2, h - 20), text, font=_font(max(18, h // 22)), fill=(255, 235, 120), anchor="ms", stroke_width=2, stroke_fill=(0, 0, 0))
    return canvas
