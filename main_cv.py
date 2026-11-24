"""OpenCV 창으로 띄우는 실행 파일 (main.py의 Tkinter 대신).

구형 Tk(8.5)에서 창이 비어 보일 때 쓴다. 동작 순서(booth.py)와 화면 그리기(render.py)는 그대로이고
'창을 띄우고 터치/키를 받는 부분'만 다르다.

  python main_cv.py               창 모드
  python main_cv.py --fullscreen  전체화면

터치(마우스 클릭): 화면의 버튼을 누른다.
키보드: SPACE 시작/다음, 1~4 필터, 1/4 이외 모드는 화면에서 선택, b 뒤로, ESC 또는 q 종료
        (키는 창을 한 번 클릭해 포커스를 준 뒤 눌러야 한다)
"""
import argparse

import cv2
import numpy as np

from booth import Booth
from button import Button
from camera import Camera
from filters import FilterBank
from hand_gesture import HandGesture
from printer import ThermalPrinter
from render import FILTER_ORDER, hit_test, render

WINDOW = "Photobooth"
SIZE = (800, 480)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()

    camera, button, printer = Camera(), Button(), ThermalPrinter()
    gesture, filters = HandGesture(), FilterBank()
    booth = Booth(camera, button, printer, gesture, filters)

    print(f"camera : {getattr(camera, 'label', 'camera') if camera.is_real else 'FAKE (no camera)'}")
    print(f"button : {'GPIO' if button.available else 'keyboard SPACE / touch only'}")
    print(f"printer: {'USB thermal printer' if printer.is_real else 'VIRTUAL (saves PNG to output/)'}")
    print(f"hand   : {'ON' if gesture.available else 'OFF (' + str(gesture.error)[:80] + ')'}")

    shown = {"size": SIZE, "state": booth.state}

    def on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        action = hit_test(x, y, shown["size"], shown["state"])
        if action:
            booth.handle(action)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, on_mouse)
    if args.fullscreen:
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(WINDOW, *SIZE)
    try:
        while True:
            try:
                _, _, ww, wh = cv2.getWindowImageRect(WINDOW)       # 창의 실제 크기 (그림과 터치 좌표를 1:1로 맞춘다)
            except cv2.error:
                ww = wh = 0
            size = (ww, wh) if ww > 0 and wh > 0 else SIZE
            frame = booth.tick()
            shown["size"], shown["state"] = size, frame.state
            img = render(frame, size)                                # PIL(RGB) 한 장
            cv2.imshow(WINDOW, cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))   # OpenCV는 BGR 순서
            key = cv2.waitKey(20) & 0xFF
            if key == 32:
                button.press()
            elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
                booth.handle(("filter", FILTER_ORDER[key - ord("1")]))
            elif key == ord("b"):
                booth.handle(("back",))
            elif key in (27, ord("q")):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
