import ctypes
import time

# Win32 SendInput Structures & Constants
PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# Hardware Scan Codes for DirectInput / Roblox ('1'..'6')
SCAN_CODES = {
    1: 0x02,  # '1'
    2: 0x03,  # '2'
    3: 0x04,  # '3'
    4: 0x05,  # '4'
    5: 0x06,  # '5'
    6: 0x07   # '6'
}

def _send_input(flags):
    extra = ctypes.c_ulong(0)
    ii_ = INPUT_UNION()
    ii_.mi = MOUSEINPUT(0, 0, 0, flags, 0, ctypes.pointer(extra))
    cmd = INPUT(ctypes.c_ulong(INPUT_MOUSE), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))

class MouseController:
    """Low-latency Win32 mouse & hardware keyboard controller."""
    def __init__(self):
        self.is_down = False

    def press(self):
        if not self.is_down:
            _send_input(MOUSEEVENTF_LEFTDOWN)
            self.is_down = True

    def release(self):
        if self.is_down:
            _send_input(MOUSEEVENTF_LEFTUP)
            self.is_down = False

    def click_at(self, x, y):
        """Move cursor to (x, y) and perform a quick click."""
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        _send_input(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.03)
        _send_input(MOUSEEVENTF_LEFTUP)
        self.is_down = False

    def force_release(self):
        """Unconditionally release left mouse button."""
        _send_input(MOUSEEVENTF_LEFTUP)
        _send_input(MOUSEEVENTF_LEFTUP)
        self.is_down = False

    def drag_and_drop(self, from_pos, to_pos, duration=0.40):
        """Smoothly drag from from_pos to to_pos by holding LMB with DirectX/Roblox mouse move events."""
        fx, fy = int(from_pos[0]), int(from_pos[1])
        tx, ty = int(to_pos[0]), int(to_pos[1])

        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        def move_cursor_event(x, y):
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
            abs_x = int(x * 65535 / screen_w)
            abs_y = int(y * 65535 / screen_h)
            ctypes.windll.user32.mouse_event(0x0001 | 0x8000, abs_x, abs_y, 0, 0)

        # Move to item slot center
        move_cursor_event(fx, fy)
        time.sleep(0.10)
        
        # Press left mouse down
        _send_input(MOUSEEVENTF_LEFTDOWN)
        self.is_down = True

        # CRITICAL: Hold in place for 0.18s so Roblox UI registers item drag pickup
        time.sleep(0.18)

        # Smooth movement interpolation to target position with real move events
        steps = 25
        step_delay = max(duration / steps, 0.010)
        for i in range(1, steps + 1):
            cx = int(fx + (tx - fx) * (i / steps))
            cy = int(fy + (ty - fy) * (i / steps))
            move_cursor_event(cx, cy)
            time.sleep(step_delay)

        # Hold over trash target for 0.15s before releasing
        time.sleep(0.15)

        # Release left mouse button twice
        _send_input(MOUSEEVENTF_LEFTUP)
        _send_input(MOUSEEVENTF_LEFTUP)
        self.is_down = False
        time.sleep(0.10)

    def press_number_key(self, num_str):
        """Presses hardware scan code for number keys '1'..'6' (DirectInput / Roblox compatible)."""
        try:
            val = int(num_str)
            scan_code = SCAN_CODES.get(val, 0)
            if scan_code:
                extra = ctypes.c_ulong(0)
                # KEY DOWN (Hardware Scan Code)
                ki_down = KEYBDINPUT(0, scan_code, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
                cmd_down = INPUT(ctypes.c_ulong(INPUT_KEYBOARD), INPUT_UNION(ki=ki_down))
                ctypes.windll.user32.SendInput(1, ctypes.pointer(cmd_down), ctypes.sizeof(cmd_down))
                time.sleep(0.06)

                # KEY UP (Hardware Scan Code)
                ki_up = KEYBDINPUT(0, scan_code, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
                cmd_up = INPUT(ctypes.c_ulong(INPUT_KEYBOARD), INPUT_UNION(ki=ki_up))
                ctypes.windll.user32.SendInput(1, ctypes.pointer(cmd_up), ctypes.sizeof(cmd_up))
                time.sleep(0.08)
        except Exception as e:
            print(f"Keypress error: {e}")


class PIDController:
    """
    Hysteresis & Momentum Controller tuned for tracking the fish icon with a physics-based slider bar.
    - Holding LMB accelerates the bar right.
    - Releasing LMB lets gravity/momentum drop the bar left.
    - Eliminates M1 click chattering during minigame.
    """
    def __init__(self, kp=0.08, kd=0.05, kv=0.03, target_offset=0):
        self.kp = kp
        self.kd = kd
        self.kv = kv
        self.target_offset = target_offset
        self.prev_error = 0.0
        self.prev_time = time.time()
        self.current_state = False

    def reset(self):
        """Resets tracking state on minigame start."""
        self.prev_error = 0.0
        self.prev_time = time.time()
        self.current_state = False

    def update(self, fish_x, bar_x, fish_vel=0.0):
        """
        Returns True if mouse should be PRESSED, False if RELEASED.
        Uses Hysteresis window (-4px to +8px) to track smoothly without spam clicking.
        """
        now = time.time()
        dt = max(now - self.prev_time, 0.001)
        self.prev_time = now

        target_x = fish_x + self.target_offset
        error = target_x - bar_x

        # Hysteresis switching:
        # Upper threshold to start holding LMB
        if error > 8.0:
            self.current_state = True
        # Lower threshold to release LMB
        elif error < -4.0:
            self.current_state = False
        # Inside deadband (-4.0 <= error <= 8.0): maintain current hold/release state

        return self.current_state, error, 0.0
