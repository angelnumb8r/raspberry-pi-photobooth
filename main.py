"""실행 파일. 화면(Tkinter)을 띄우고 booth.tick()을 일정 간격으로 호출한다.

  python main.py              전체화면(라즈베리파이)
  python main.py --windowed   창 모드(개발용)
  SPACE: 버튼 대신 촬영 시작 / ESC: 종료
"""
import argparse
import tkinter as tk

from PIL import ImageTk

from booth import Booth
from button import Button
from camera import Camera
from filters import FilterBank
from hand_gesture import HandGesture
from printer import ThermalPrinter
from render import render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--windowed", action="store_true")
    args = parser.parse_args()

    camera, button, printer = Camera(), Button(), ThermalPrinter()
    gesture, filters = HandGesture(), FilterBank()
    booth = Booth(camera, button, printer, gesture, filters)

    # 시작할 때 무엇이 실제 장치이고 무엇이 대체(가상)인지 터미널에 알려 준다
    print(f"camera : {'USB camera' if camera.is_real else 'FAKE (no camera)'}")
    print(f"button : {'GPIO' if button.available else 'keyboard SPACE only'}")
    print(f"printer: {'USB thermal printer' if printer.is_real else 'VIRTUAL (saves PNG to output/)'}")
    print(f"hand   : {'ON' if gesture.available else 'OFF (' + str(gesture.error)[:80] + ')'}")

    root = tk.Tk()
    root.title("Photobooth")
    root.configure(bg="black")
    if not args.windowed:
        root.attributes("-fullscreen", True)
    else:
        root.geometry("800x600")
    label = tk.Label(root, bg="black")
    label.pack(fill="both", expand=True)
    root.bind("<space>", lambda e: button.press())
    root.bind("<Escape>", lambda e: root.destroy())

    def loop():
        frame = booth.tick()
        size = (max(label.winfo_width(), 320), max(label.winfo_height(), 240))
        photo = ImageTk.PhotoImage(render(frame, size))
        label.configure(image=photo)
        label.image = photo                   # 참조를 유지하지 않으면 이미지가 사라진다
        root.after(30, loop)

    loop()
    try:
        root.mainloop()
    finally:
        camera.close()


if __name__ == "__main__":
    main()
