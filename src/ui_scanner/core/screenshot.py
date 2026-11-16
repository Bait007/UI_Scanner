import os
import subprocess
import atexit
from typing import Tuple, Optional
import mss
from PIL import Image
from ..config import IS_WINDOWS, IS_LINUX

_sct = mss.mss()
atexit.register(_sct.close)


def take_screenshot() -> Tuple[Optional[Image.Image], int, int, int, int]:
    try:
        # Windows или Linux X11
        if IS_WINDOWS or (IS_LINUX and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"):
            monitor = _sct.monitors[0]
            shot = _sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            left = monitor["left"]
            top = monitor["top"]

        # Linux Wayland
        elif IS_LINUX:
            tmp_path = "/dev/shm/ui_scanner_screen.png"

            subprocess.run(
                ["gnome-screenshot", "-f", tmp_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            img = Image.open(tmp_path)
            left = 0
            top = 0
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        else:
            raise RuntimeError("Unsupported OS")

        return img, left, top, img.width, img.height

    except Exception:
        return None, 0, 0, 0, 0
