"""
Захватываем миникарту в правом‑нижнем углу экрана (16:9).
– Точка (left, top) = (screen_w - W, screen_h - H)
– Каждые 0.15 с кладём картинку в глобальную переменную LAST_MINIMAP.
"""
import cv2, numpy as np, os
from mss import mss
from time import sleep
from threading import Thread
import ctypes

# 1. Узнаём реальное разрешение рабочего стола
user32 = ctypes.windll.user32
SCREEN_W, SCREEN_H = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

# 2. Размер миникарты под стандартное 16:9 (поправьте при другом GUI‑scale)
W, H = 300, 270
MONITOR = {"left": SCREEN_W - W, "top": SCREEN_H - H, "width": W, "height": H}

LAST_MINIMAP = None  # глобальное хранилище картинки

def capture_loop():
    global LAST_MINIMAP
    with mss() as sct:
        while True:
            img = np.array(sct.grab(MONITOR))
            LAST_MINIMAP = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            sleep(0.15)

def start():
    Thread(target=capture_loop, daemon=True).start()
