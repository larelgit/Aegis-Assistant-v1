#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screenshot.py — experimental minimap capture (Windows-only).

Captures the bottom-right corner of the screen (minimap in 16:9 Dota 2).
Stores the latest frame in LAST_MINIMAP for potential future CV processing.

NOTE: This module is OPTIONAL. Enable via --capture-minimap flag in runtime_server.py.
      Requires: opencv-python, mss, ctypes (Windows)
"""

import ctypes
from threading import Thread
from time import sleep

import cv2
import numpy as np
from mss import mss

# Detect real desktop resolution (Windows)
user32 = ctypes.windll.user32
SCREEN_W = user32.GetSystemMetrics(0)
SCREEN_H = user32.GetSystemMetrics(1)

# Minimap region (standard 16:9, adjust for different GUI scales)
W, H = 300, 270
MONITOR = {"left": SCREEN_W - W, "top": SCREEN_H - H, "width": W, "height": H}

LAST_MINIMAP = None  # global frame storage


def capture_loop():
    global LAST_MINIMAP
    with mss() as sct:
        while True:
            img = np.array(sct.grab(MONITOR))
            LAST_MINIMAP = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            sleep(0.15)


def start():
    Thread(target=capture_loop, daemon=True).start()
