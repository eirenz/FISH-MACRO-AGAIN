# FISH-MACRO-AGAIN 🎣

A high-performance, automated Python fishing macro equipped with:
- **Vision-Based Minigame Tracking:** Tracks blue capture bar and fish position at 100+ FPS using `mss` and `OpenCV`.
- **Adaptive Velocity Control:** PID controller with velocity feed-forward ($K_v$) to adapt to fast bar movements and prevent overshooting.
- **Continuous Storm-Fishing M1 Clicker:** Spam-clicks LMB while waiting for bites and instantly switches to minigame tracking upon UI appearance.
- **Hotbar Inventory & Tome Removal:** Scans hotbar slots 1–6, double-clicks all items, and automatically drags **Tome** items to the Trash Can button.
- **Modern Tkinter Dashboard GUI:** Click-and-drag overlays for spot/ROI calibration, live sensitivity sliders, real-time visual tracker preview, and global hotkeys (`F5` Start/Pause, `F8` Emergency Stop).

---

## 🚀 Quick Start

### 1. Requirements
Python 3.10+ with required libraries:
```bash
pip install opencv-python numpy mss pynput pillow
```

### 2. Launch Macro
```bash
python main.py
```

---

## 📍 Setup & Calibration

In the GUI Dashboard under **Calibration Setup**:
1. **Set Cast Spot:** Click your in-game fishing spot.
2. **Set Minigame ROI:** Click and drag a box around the minigame bar.
3. **Set Hotbar ROI:** Click and drag a box around slots 1–6.
4. **Set Trash Button:** Click your in-game Trash Can icon.

Press **F5** to start auto-fishing!
