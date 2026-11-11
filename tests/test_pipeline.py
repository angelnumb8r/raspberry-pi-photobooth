"""하드웨어 없이 돌려 볼 수 있는 검증. 실행: python tests/test_pipeline.py"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
config.FAKE_CAMERA_IMAGE = "tests/sample.jpg"
config.COUNTDOWN_SECONDS = 3
config.RESULT_SECONDS = 1
config.DETECT_EVERY_N_FRAMES = 1
config.GESTURE_STABLE_FRAMES = 2

from PIL import Image
from booth import Booth, State
from button import Button
from camera import Camera
from face_sticker import FaceSticker
from filters import FilterBank
from hand_gesture import Stabilizer, count_fingers
from image_utils import to_printable
from printer import ThermalPrinter
from render import render

P = lambda x, y: types.SimpleNamespace(x=x, y=y)


def fake_hand(extended):
    """손목(0.5, 0.9)에서 위로 뻗은 손. extended: 펴진 손가락 이름 집합."""
    pts = [P(0.5, 0.9) for _ in range(21)]
    cols = {"index": (8, 6, 0.42), "middle": (12, 10, 0.5), "ring": (16, 14, 0.58), "pinky": (20, 18, 0.66)}
    for name, (tip, pip, x) in cols.items():
        pts[pip] = P(x, 0.62)
        pts[tip] = P(x, 0.35) if name in extended else P(x, 0.70)   # 펴짐: 멀리 / 접힘: 손바닥 쪽
    return pts


def test_count_fingers():
    cases = [(set(), 0), ({"index"}, 1), ({"index", "middle"}, 2), ({"index", "middle", "ring"}, 3),
             ({"index", "middle", "ring", "pinky"}, 4), ({"pinky"}, 1)]
    for ext, want in cases:
        got = count_fingers(fake_hand(ext))
        assert got == want, (ext, got, want)
    # 손이 90도 기울어도(좌우 방향) 같은 결과
    rot = [P(1 - p.y, p.x) for p in fake_hand({"index", "middle"})]
    assert count_fingers(rot) == 2
    print("PASS count_fingers (6 cases + rotation)")


def test_stabilizer():
    s = Stabilizer(n=3, initial="basic")
    seq = ["cat", "basic", "cat", "cat", "cat", "sketch", "cat"]
    out = [s.update(x) for x in seq]
    assert out == ["basic", "basic", "basic", "basic", "cat", "cat", "cat"], out
    print("PASS stabilizer (한두 프레임 오인식 무시)")


def test_filters_and_print():
    img = Image.open("tests/sample.jpg").convert("RGB")
    bank = FilterBank()
    face = FaceSticker().detect_face(img)
    assert face is not None, "샘플 사진에서 얼굴을 못 찾음"
    for name in ("basic", "contrast", "sketch", "cat"):
        out, msg = bank.apply(name, img)
        assert out.size == img.size
        printable = to_printable(out)
        assert printable.mode == "1" and printable.width == config.PRINT_WIDTH
        printable.save(f"output/test_{name}.png")
        out.save(f"output/test_{name}_color.png")
        print(f"PASS filter {name:9s} msg={msg!r} -> printable {printable.size}")
    out, msg = bank.apply("cat", Image.new("RGB", (400, 400), (128, 128, 128)))
    assert msg == "No face found"
    print("PASS cat filter on empty image -> 'No face found'")
    pr = ThermalPrinter()
    path = pr.print_image(printable)
    assert os.path.exists(path) and pr.raw_size() > 1000
    print(f"PASS virtual printer: saved {os.path.basename(path)}, ESC/POS bytes={pr.raw_size()}")


class StubGesture:
    available = True
    def __init__(self): self.fingers = 0
    def detect(self, frame): return self.fingers


def test_state_machine():
    cam, btn, pr, gest = Camera(), Button(), ThermalPrinter(), StubGesture()
    assert cam.is_real is False and btn.available is False
    booth = Booth(cam, btn, pr, gest, FilterBank())
    t = 100.0
    # 손가락 2개 -> 안정화(2프레임) 후 cat
    gest.fingers = 2
    for _ in range(3):
        f = booth.tick(t); t += 0.03
    assert booth.filter_name == "cat" and f.state is State.IDLE
    # 버튼 -> 카운트다운 3,2,1
    btn.press(); f = booth.tick(t); t += 0.03
    assert f.state is State.COUNTDOWN
    seen = []
    while f.state is State.COUNTDOWN:
        f = booth.tick(t); seen.append(f.big_text); t += 0.25
    assert [s for i, s in enumerate(seen) if s and (i == 0 or s != seen[i-1])] == ["3", "2", "1"], seen
    assert f.state is State.RESULT
    # 카운트다운 중 손 모양이 바뀌어도 필터는 고정, 버튼 중복 입력은 무시
    btn.press(); f = booth.tick(t); t += 0.03
    assert f.state is State.RESULT
    before = len(os.listdir("output"))
    while f.state in (State.RESULT, State.PRINTING):
        f = booth.tick(t); t += 0.3
        import time; time.sleep(0.01)
    assert f.state is State.IDLE
    assert len(os.listdir("output")) == before + 1, "가상 프린터 출력 파일이 생성되지 않음"
    # 프린터 오류 -> 오류 안내 후 대기 복귀
    class BadPrinter(ThermalPrinter):
        def print_image(self, img): raise RuntimeError("no paper")
    booth2 = Booth(cam, btn, BadPrinter(), gest, FilterBank())
    t = 200.0
    booth2.tick(t); btn.press()
    while True:
        t += 0.3; f = booth2.tick(t); time.sleep(0.01)
        if booth2.state is State.IDLE and booth2._print_thread is not None: break
    f = booth2.tick(t)
    assert "Printer error" in f.notice, f.notice
    print("PASS state machine: IDLE->COUNTDOWN(3,2,1)->RESULT->PRINTING->IDLE, 중복 입력 무시, 프린터 오류 복구")


def test_render():
    cam, btn = Camera(), Button()
    booth = Booth(cam, btn, ThermalPrinter(), StubGesture(), FilterBank())
    f = booth.tick(0.0)
    render(f, (800, 600)).save("output/screen_idle.png")
    btn.press(); booth.tick(0.1); f = booth.tick(0.5)
    render(f, (800, 600)).save("output/screen_countdown.png")
    print("PASS render (screen_idle.png, screen_countdown.png)")


def test_mediapipe_api():
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    vision.HandLandmarkerOptions(base_options=mp_python.BaseOptions(model_asset_path="x.task"),
                                 running_mode=vision.RunningMode.IMAGE, num_hands=1)
    from hand_gesture import HandGesture
    h = HandGesture("models/not_there.task")
    assert h.available is False and h.detect(None) is None
    print("PASS mediapipe options build; 모델 파일이 없으면 손 인식만 꺼지고 나머지는 동작")


if __name__ == "__main__":
    test_count_fingers(); test_stabilizer(); test_filters_and_print()
    test_state_machine(); test_render(); test_mediapipe_api()
    print("ALL PASSED")
