"""감열 프린터 출력(ESC/POS). 실제 프린터가 없으면 가상 프린터로 동작한다.

가상 프린터도 python-escpos의 Dummy를 거치므로, 실제 프린터에 보낼 명령(바이트)이
만들어지는 경로를 실물 없이 똑같이 검증할 수 있다. 결과 이미지는 파일로 저장한다.
"""
import os
import time

import config


class ThermalPrinter:
    def __init__(self, usb_ids=config.PRINTER_USB_IDS, out_dir=config.OUTPUT_DIR):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.is_real = usb_ids is not None
        if self.is_real:
            from escpos.printer import Usb
            self._p = Usb(usb_ids[0], usb_ids[1])
        else:
            from escpos.printer import Dummy
            self._p = Dummy()

    def print_image(self, img_1bit):
        """1비트 PIL 이미지를 인쇄한다. 저장한 파일 경로(가상) 또는 None(실물)을 반환."""
        path = None
        if not self.is_real:
            stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"   # 같은 초에 두 번 찍어도 덮어쓰지 않게
            path = os.path.join(self.out_dir, f"print_{stamp}.png")
            img_1bit.save(path)
        self._p.image(img_1bit, center=False)
        self._p.ln(3)              # 용지를 몇 줄 밀어 내서 사진이 잘려 나오게 함
        return path

    def raw_size(self):
        """가상 프린터가 만든 명령 바이트 수 (검증용)."""
        return len(self._p.output) if not self.is_real else None
