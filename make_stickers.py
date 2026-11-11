"""고양이 스티커(귀/코/수염)를 PNG(투명 배경)로 생성한다.

감열 프린터는 흑백 점(1비트)으로 인쇄하므로
- 굵은 검은 외곽선 + 흰색 채움  → 흑백 변환 후에도 형태가 선명함
- 회색/반투명 같은 중간 톤은 쓰지 않음  → 디더링 시 지저분한 점무늬가 됨
이 원칙으로 그린다. 4배 크게 그린 뒤 줄여서 선이 매끄럽게 나오게 한다(슈퍼샘플링).
"""
from PIL import Image, ImageDraw

SS = 4  # supersampling 배율
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)


def _canvas(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def _finish(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


def cat_ears(w=600, h=260):
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    lw = 14 * SS

    def ear(base_l, base_r, tip, inner_l, inner_r, inner_tip):
        pts = [(x * SS, y * SS) for x, y in (base_l, tip, base_r)]
        d.polygon(pts, fill=WHITE)
        d.line(pts + [pts[0]], fill=BLACK, width=lw, joint="curve")
        ipts = [(x * SS, y * SS) for x, y in (inner_l, inner_tip, inner_r)]
        d.polygon(ipts, fill=BLACK)

    # 왼쪽 귀 / 오른쪽 귀 (좌우 대칭)
    ear((40, 250), (270, 250), (110, 20), (95, 225), (215, 225), (125, 85))
    ear((330, 250), (560, 250), (490, 20), (385, 225), (505, 225), (475, 85))
    return _finish(img, w, h)


def cat_nose(w=140, h=110):
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    # 코: 아래로 향한 둥근 삼각형 + 입(역 Y자)
    nose = [(25 * SS, 12 * SS), (115 * SS, 12 * SS), (70 * SS, 58 * SS)]
    d.polygon(nose, fill=BLACK)
    lw = 8 * SS
    d.line([(70 * SS, 58 * SS), (70 * SS, 82 * SS)], fill=BLACK, width=lw)
    d.arc([(22 * SS, 60 * SS), (70 * SS, 100 * SS)], 0, 90, fill=BLACK, width=lw)
    d.arc([(70 * SS, 60 * SS), (118 * SS, 100 * SS)], 90, 180, fill=BLACK, width=lw)
    return _finish(img, w, h)


def cat_whiskers(w=900, h=200):
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    lw = 15 * SS   # 인쇄에서 가늘면 끊겨 보이므로 굵게
    # 가운데 220px는 코가 들어갈 자리라 비워 둔다
    for y0, y1 in ((60, 20), (100, 100), (140, 180)):
        d.line([(20 * SS, y0 * SS), (300 * SS, (100 + (y0 - 100) * 0.3) * SS)], fill=BLACK, width=lw)
        d.line([((w - 20) * SS, y0 * SS), ((w - 300) * SS, (100 + (y0 - 100) * 0.3) * SS)], fill=BLACK, width=lw)
    return _finish(img, w, h)


if __name__ == "__main__":
    cat_ears().save("assets/cat_ears.png")
    cat_nose().save("assets/cat_nose.png")
    cat_whiskers().save("assets/cat_whiskers.png")
    print("saved: assets/cat_ears.png, cat_nose.png, cat_whiskers.png")
