import argparse

import cv2
import numpy as np

from booth import Booth
from button import Button
from camera import Camera
from filters import FilterBank
from hand_gesture import HandGesture
from printer import ThermalPrinter
from render import render

WINDOW = "Photobooth"
SIZE = (800, 600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()

    camera, button, printer = Camera(), Button(), ThermalPrinter()
    gesture, filters = HandGesture(), FilterBank()
    booth = Booth(camera, button, printer, gesture, filters)

    print(f"camera : {'USB camera' if camera.is_real else 'FAKE (no camera)'}")
    print(f"button : {'GPIO' if button.available else 'keyboard SPACE only'}")
    print(f"printer: {'USB thermal printer' if printer.is_real else 'VIRTUAL (saves PNG to output/)'}")
    print(f"hand   : {'ON' if gesture.available else 'OFF (' + str(gesture.error)[:80] + ')'}")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    if args.fullscreen:
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(WINDOW, *SIZE)
    try:
        while True:
            img = render(booth.tick(), SIZE)
            cv2.imshow(WINDOW, cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
            key = cv2.waitKey(30) & 0xFF
            if key == 32:
                button.press()
            elif key in (27, ord("q")):
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
