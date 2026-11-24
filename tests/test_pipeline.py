"""하드웨어 없이 돌려 볼 수 있는 검증. 실행: python tests/test_pipeline.py"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
config.FAKE_CAMERA_IMAGE = "tests/sample.jpg"
config.COUNTDOWN_SECONDS = 3
config.FLASH_SECONDS = 0.12
config.INTERVAL_SECONDS = 1.2
config.DONE_SECONDS = 10
config.IDLE_SECONDS = 60
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
from render import hit_test, render
import time

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


def run_until(booth, t, pred, step=0.05, limit=60.0):
    """가짜 시계로 pred(frame)가 참이 될 때까지 tick을 돌린다. (frame, 시각) 반환."""
    end = t + limit
    while t < end:
        f = booth.tick(t)
        if pred(f):
            return f, t
        t += step
        time.sleep(0.002)          # 인쇄 스레드가 돌 틈을 준다
    raise AssertionError("시간 초과: 기대한 상태에 도달하지 못함")


def test_state_machine():
    cam, btn, pr, gest = Camera(), Button(), ThermalPrinter(), StubGesture()
    assert cam.is_real is False and btn.available is False
    booth = Booth(cam, btn, pr, gest, FilterBank())
    t = 100.0
    f = booth.tick(t)
    assert f.state is State.HOME
    # 홈에서 아무 데나 누르면 선택 화면, 1컷/4컷 중 고르면 촬영 대기(LIVE)
    booth.handle(("primary",), t)
    assert booth.state is State.SELECT
    booth.handle(("mode", 4), t)
    assert booth.state is State.LIVE and booth.mode == 4
    # 필터: 손가락 2개 -> 안정화 후 cat, 터치로 고른 필터는 손이 안 보여도 유지
    gest.fingers = 2
    for _ in range(3):
        f = booth.tick(t); t += 0.03
    assert booth.filter_name == "cat"
    booth.handle(("filter", "sketch"), t)
    gest.fingers = None
    for _ in range(5):
        booth.tick(t); t += 0.03
    assert booth.filter_name == "sketch", "손이 안 보일 때 터치로 고른 필터가 덮어써짐"
    # 한 번 누르면 4컷이 자동으로 이어진다: 카운트다운(3,2,1) -> 플래시 -> 간격 -> ... -> 배출
    before = len(os.listdir("output"))
    booth.handle(("primary",), t)
    nums, states, shots = [], [], []
    while booth.state is not State.EJECT:
        f = booth.tick(t); t += 0.05
        time.sleep(0.002)
        if not states or states[-1] is not f.state:
            states.append(f.state)
        if f.state is State.COUNTDOWN:
            import math
            n = math.ceil(f.remaining)
            if not nums or nums[-1] != n:
                nums.append(n)
        if f.state is State.COUNTDOWN and f.shots_done not in shots:
            shots.append(f.shots_done)
        assert t < 200, "촬영이 끝나지 않음"
    assert shots == [0, 1, 2, 3], shots
    assert nums == [3, 2, 1] * 4, nums
    assert states.count(State.FLASH) == 4 and states.count(State.INTERVAL) == 3, states
    # 촬영 도중 추가 입력(primary)은 무시된다 (이미 EJECT 상태)
    booth.handle(("primary",), t)
    assert booth.state is State.EJECT
    f, t = run_until(booth, t, lambda f: f.state is State.DONE)
    assert f.strip is not None and f.strip.mode == "1" and f.strip.width == config.PRINT_WIDTH
    assert f.strip.height > f.strip.width * 2, "4컷 스트립은 세로로 길어야 함"
    assert len(os.listdir("output")) == before + 1, "가상 프린터 출력 파일이 생성되지 않음"
    # 완료 화면에서 누르면 홈으로, 사진은 메모리에서 지워진다
    booth.handle(("primary",), t)
    assert booth.state is State.HOME and booth._shots == [] and booth._strip is None
    # 완료 화면을 그냥 두면 자동으로 홈으로
    booth.handle(("primary",), t); booth.handle(("mode", 1), t); booth.handle(("primary",), t)
    f, t = run_until(booth, t, lambda f: f.state is State.DONE)
    assert f.mode == 1 and f.strip.height < f.strip.width * 1.5
    f, t = run_until(booth, t, lambda f: f.state is State.HOME, limit=config.DONE_SECONDS + 2)
    # 아무도 없으면 LIVE/SELECT -> HOME
    booth.handle(("primary",), t); f, t = run_until(booth, t, lambda f: f.state is State.HOME, limit=70)
    # 프린터 오류 -> 안내를 띄운 뒤에도 흐름은 끝까지 간다
    class BadPrinter(ThermalPrinter):
        def print_image(self, img): raise RuntimeError("no paper")
    booth2 = Booth(cam, btn, BadPrinter(), gest, FilterBank())
    booth2.mode = 1
    booth2.handle(("primary",), t); booth2.handle(("mode", 1), t); booth2.handle(("primary",), t)
    f, t = run_until(booth2, t, lambda f: f.state is State.DONE)
    assert "PRINTER ERROR" in f.notice, f.notice
    print("PASS state machine: HOME->SELECT->LIVE->(COUNTDOWN->FLASH->INTERVAL)x4->EJECT->DONE->HOME, "
          "필터 유지, 대기 복귀, 프린터 오류 안내")


def test_hit_test():
    size = (1280, 720)
    s = min(1280 / 800, 720 / 480)
    ox, oy = (1280 - 800 * s) / 2, (720 - 480 * s) / 2
    px = lambda x, y: (ox + x * s, oy + y * s)
    assert hit_test(*px(400, 240), size, State.HOME) == ("primary",)
    assert hit_test(*px(250, 240), size, State.SELECT) == ("mode", 1)
    assert hit_test(*px(550, 240), size, State.SELECT) == ("mode", 4)
    assert hit_test(*px(400, 410), size, State.SELECT) == ("back",)
    assert hit_test(*px(660, 140), size, State.LIVE) == ("filter", "contrast")
    assert hit_test(*px(660, 320), size, State.LIVE) == ("primary",)
    assert hit_test(*px(660, 384), size, State.LIVE) == ("back",)
    assert hit_test(*px(200, 200), size, State.LIVE) is None          # 사진 영역은 무반응
    assert hit_test(*px(660, 320), size, State.COUNTDOWN) is None     # 촬영 중에는 터치 무시
    assert hit_test(*px(660, 320), size, State.EJECT) is None
    assert hit_test(*px(400, 240), size, State.DONE) == ("primary",)
    print("PASS hit_test (1280x720 가로 여백 포함 11 cases)")


def test_render():
    import render as R
    cam, btn = Camera(), Button()
    booth = Booth(cam, btn, ThermalPrinter(), StubGesture(), FilterBank())
    t = 0.0
    saved = {}
    def snap(name, f):
        render(f, (800, 480)).save(f"output/screen_{name}.png"); saved[name] = f
    snap("home", booth.tick(t))
    booth.handle(("primary",), t); snap("select", booth.tick(t))
    booth.handle(("mode", 4), t); snap("live", booth.tick(t))
    booth.handle(("primary",), t)
    for _ in range(10): f = booth.tick(t); t += 0.05
    snap("countdown", f)
    while booth.state is not State.FLASH: f = booth.tick(t); t += 0.05
    snap("flash", f)
    while booth.state is not State.INTERVAL: f = booth.tick(t); t += 0.05
    snap("interval", booth.tick(t))
    while booth.state is not State.EJECT: f = booth.tick(t); t += 0.05
    t_eject = t
    for name, at in (("eject_a", 0.3), ("eject_b", 0.6), ("eject_c", 1.5), ("eject_d", 3.0)):
        f = booth.tick(t_eject + at); snap(name, f)
    while booth.state is not State.DONE: f = booth.tick(t); t += 0.05; time.sleep(0.002)
    snap("done", f)
    # 해상도별 크기, 시간
    for size in ((800, 480), (1280, 720), (1920, 1080), (1024, 600)):
        img = render(f, size); assert img.size == size
    t0 = time.perf_counter()
    for _ in range(20): render(f, (1920, 1080))
    ms = (time.perf_counter() - t0) / 20 * 1000
    print(f"PASS render 8 states + eject frames (output/screen_*.png), 1080p {ms:.1f} ms/frame")


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
    test_state_machine(); test_hit_test(); test_render(); test_mediapipe_api()
    print("ALL PASSED")
