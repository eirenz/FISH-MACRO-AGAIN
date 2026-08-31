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

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", INPUT_UNION)
    ]

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000

def _send_input(flags):
    extra = ctypes.c_ulong(0)
    ii_ = INPUT_UNION()
    ii_.mi = MOUSEINPUT(0, 0, 0, flags, 0, ctypes.pointer(extra))
    cmd = INPUT(ctypes.c_ulong(INPUT_MOUSE), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))

class MouseController:
    """Low-latency Win32 mouse controller."""
    def __init__(self):
        self.is_down = False

    def press(self):
        if not self.is_down:
            _send_input(MOUSEEVENTF_LEFTDOWN)
            self.is_down = True

    def release(self):
        # Always issue UP event to avoid state desync
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

    def drag_and_drop(self, from_pos, to_pos, duration=0.25):
        """Smoothly drag from from_pos to to_pos by holding LMB."""
        fx, fy = int(from_pos[0]), int(from_pos[1])
        tx, ty = int(to_pos[0]), int(to_pos[1])

        # Move to start position
        ctypes.windll.user32.SetCursorPos(fx, fy)
        time.sleep(0.05)
        
        # Hold left mouse down
        _send_input(MOUSEEVENTF_LEFTDOWN)
        self.is_down = True
        time.sleep(0.05)

        # Smooth movement interpolation
        steps = 15
        step_delay = max(duration / steps, 0.005)
        for i in range(1, steps + 1):
            cx = int(fx + (tx - fx) * (i / steps))
            cy = int(fy + (ty - fy) * (i / steps))
            ctypes.windll.user32.SetCursorPos(cx, cy)
            time.sleep(step_delay)

        time.sleep(0.05)
        _send_input(MOUSEEVENTF_LEFTUP)
        _send_input(MOUSEEVENTF_LEFTUP)
        self.is_down = False
        time.sleep(0.05)


class PIDController:
    """
    PID Controller tuned for tracking the fish icon with a physics-based slider bar.
    - Pressing LMB accelerates the bar right.
    - Releasing LMB lets gravity/momentum drop the bar left.
    """
    def __init__(self, kp=0.08, kd=0.05, kv=0.03, target_offset=0):
        self.kp = kp
        self.kd = kd
        self.kv = kv
        self.target_offset = target_offset
        self.prev_error = 0.0
        self.prev_time = time.time()
        self.filtered_derivative = 0.0

    def update(self, fish_x, bar_x, fish_vel=0.0):
        """
        Returns True if mouse should be PRESSED, False if RELEASED.
        """
        now = time.time()
        dt = max(now - self.prev_time, 0.001)
        self.prev_time = now

        # Error: positive means fish is to the RIGHT of bar (need to move right -> hold LMB)
        target_x = fish_x + self.target_offset
        error = target_x - bar_x

        # Derivative: rate of error change (damping momentum)
        raw_derivative = (error - self.prev_error) / dt
        # Low-pass filter on derivative to prevent jitter
        self.filtered_derivative = 0.7 * self.filtered_derivative + 0.3 * raw_derivative
        self.prev_error = error

        # Control output signal u with velocity feedforward
        u = (self.kp * error) + (self.kd * self.filtered_derivative) + (self.kv * fish_vel)

        # Decision threshold: positive output means apply upward force (hold LMB)
        should_press = u > 0
        return should_press, error, u
