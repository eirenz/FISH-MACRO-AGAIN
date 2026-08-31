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

    def drag_and_drop(self, from_pos, to_pos, duration=0.35):
        """Smoothly drag from from_pos to to_pos by holding LMB."""
        fx, fy = int(from_pos[0]), int(from_pos[1])
        tx, ty = int(to_pos[0]), int(to_pos[1])

        # Move to item slot center
        ctypes.windll.user32.SetCursorPos(fx, fy)
        time.sleep(0.08)
        
        # Press left mouse down
        _send_input(MOUSEEVENTF_LEFTDOWN)
        self.is_down = True

        # CRITICAL: Hold in place for 0.12s so UI registers item drag pickup
        time.sleep(0.12)

        # Smooth movement interpolation to target position
        steps = 25
        step_delay = max(duration / steps, 0.008)
        for i in range(1, steps + 1):
            cx = int(fx + (tx - fx) * (i / steps))
            cy = int(fy + (ty - fy) * (i / steps))
            ctypes.windll.user32.SetCursorPos(cx, cy)
            time.sleep(step_delay)

        # Hold over trash target for 0.1s before releasing
        time.sleep(0.10)

        # Release left mouse button twice
        _send_input(MOUSEEVENTF_LEFTUP)
        _send_input(MOUSEEVENTF_LEFTUP)
        self.is_down = False
        time.sleep(0.08)

    def press_number_key(self, num_str):
        """Presses keyboard number key '1', '2', '3', '4', '5', or '6'."""
        try:
            val = int(num_str)
            if 1 <= val <= 6:
                vk = 0x30 + val  # 0x31 for '1', 0x36 for '6'
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP = 0x0002
        except Exception:
            pass


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
        self.pulse_counter = 0

    def update(self, fish_x, bar_x, fish_vel=0.0):
        """
        Returns True if mouse should be PRESSED, False if RELEASED.
        Uses deadband feathering to hover smoothly over the fish without endless LMB holding.
        """
        now = time.time()
        dt = max(now - self.prev_time, 0.001)
        self.prev_time = now

        # Target and Error calculation
        target_x = fish_x + self.target_offset
        error = target_x - bar_x

        # Rate of error change (derivative)
        raw_derivative = (error - self.prev_error) / dt
        self.filtered_derivative = 0.6 * self.filtered_derivative + 0.4 * raw_derivative
        self.prev_error = error

        self.pulse_counter = (self.pulse_counter + 1) % 6

        # Deadband feathering logic:
        if error > 18:
            # Fish is significantly to the right -> hold LMB to accelerate right
            should_press = True
        elif error < -14:
            # Fish is to the left -> release LMB completely to drop left
            should_press = False
        else:
            # Bar is ON TOP of the fish (-14 <= error <= 18): Feather/Pulse LMB
            if self.filtered_derivative < -5:
                # Bar is falling away from fish -> pulse to catch
                should_press = True
            elif self.filtered_derivative > 10:
                # Bar moving right fast -> release to prevent overshoot
                should_press = False
            else:
                # Hover pulse (press 1 frame out of 3 to counteract gravity)
                should_press = (self.pulse_counter == 0)

        # Output signal u for debug logging
        u = (self.kp * error) + (self.kd * self.filtered_derivative) + (self.kv * fish_vel)
        return should_press, error, u
