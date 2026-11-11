"""물리 버튼(GPIO). 눌림을 '요청 플래그'로만 기록한다.

왜 플래그인가: gpiozero의 콜백은 별도 스레드에서 실행되는데, Tkinter 화면은 메인 스레드에서만
안전하게 만질 수 있다. 콜백에서 화면을 직접 건드리지 않고 플래그만 세워 두면,
메인 루프가 프레임마다 확인해서 처리하므로 스레드 충돌이 없다.

GPIO를 쓸 수 없는 환경(Mac 등)에서는 조용히 비활성화되고, 화면의 SPACE 키가 대신 쓰인다.
"""
import threading

import config


class Button:
    def __init__(self, pin=config.GPIO_BUTTON_PIN, pull_up=config.BUTTON_PULL_UP):
        self._pressed = threading.Event()
        self.available = False
        try:
            from gpiozero import Button as GpioButton
            self._btn = GpioButton(pin, pull_up=pull_up, bounce_time=0.05)  # 떨림(바운스) 방지
            self._btn.when_pressed = self._pressed.set
            self.available = True
        except Exception:
            self._btn = None

    def press(self):
        """키보드 등 다른 입력에서 같은 효과를 내기 위한 함수."""
        self._pressed.set()

    def consume(self):
        """눌림이 있었으면 True를 한 번만 반환하고 플래그를 지운다."""
        if self._pressed.is_set():
            self._pressed.clear()
            return True
        return False
