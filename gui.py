import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import mss

# Config Manager Helper
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

class ConfigManager:
    def __init__(self):
        self.config = {
            "cast_pos": None,
            "minigame_roi": None,
            "cast_delay": 1.5,
            "recast_delay": 1.5,
            "kp": 0.08,
            "kd": 0.05,
            "target_offset": 0,
            "min_ui_confidence": 0.5,
            "hotkey_start": "f5",
            "hotkey_stop": "f8"
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save(self):
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def get(self):
        return self.config

    def set(self, key, value):
        self.config[key] = value
        self.save()


class SpotSelectorOverlay:
    """Full-screen overlay to select screen coordinates."""
    def __init__(self, callback, prompt="🎯 LEFT-CLICK anywhere to set location (Press ESC to cancel)"):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.35)
        self.root.attributes("-topmost", True)
        self.root.config(bg="gray")
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Instruction banner
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text=prompt,
            fill="white",
            font=("Segoe UI", 16, "bold")
        )

        self.root.lift()
        self.root.focus_force()
        try:
            self.root.grab_set()
        except Exception:
            pass

        self.root.bind("<Button-1>", self.on_click)
        self.root.bind("<Escape>", self.on_cancel)

    def on_click(self, event):
        x, y = event.x_root, event.y_root
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()
        self.callback(x, y)

    def on_cancel(self, event):
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()


class ROISelectorOverlay:
    """Full-screen overlay to select region of interest (ROI)."""
    def __init__(self, callback, prompt="📐 CLICK & DRAG to select region (Press ESC to cancel)"):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.35)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Banner
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text=prompt,
            fill="cyan",
            font=("Segoe UI", 16, "bold")
        )

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.root.lift()
        self.root.focus_force()
        try:
            self.root.grab_set()
        except Exception:
            pass

        self.root.bind("<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", self.on_cancel)

    def on_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=3)

    def on_drag(self, event):
        cur_x, cur_y = event.x_root, event.y_root
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        end_x, end_y = event.x_root, event.y_root
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()
        
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        if (x2 - x1) > 20 and (y2 - y1) > 10:
            self.callback(x1, y1, x2, y2)

    def on_cancel(self, event):
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()


class MultiStepSequenceOverlay:
    """Full-screen interactive overlay to select multiple stage reset click points in order."""
    def __init__(self, callback, prompt="🔄 LEFT-CLICK points in order | RIGHT-CLICK or ENTER when Done | ESC to Cancel"):
        self.callback = callback
        self.steps = []

        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.35)
        self.root.attributes("-topmost", True)
        self.root.config(bg="gray", cursor="cross")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Banner
        self.banner = self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text=prompt,
            fill="yellow",
            font=("Segoe UI", 15, "bold")
        )

        self.root.lift()
        self.root.focus_force()
        try:
            self.root.grab_set()
        except Exception:
            pass

        self.root.bind("<Button-1>", self.on_left_click)
        self.root.bind("<Button-3>", self.on_done)
        self.root.bind("<Return>", self.on_done)
        self.root.bind("<Escape>", self.on_cancel)

    def on_left_click(self, event):
        x, y = event.x_root, event.y_root
        self.steps.append((x, y))
        idx = len(self.steps)

        # Draw visual marker on canvas
        cx, cy = event.x, event.y
        self.canvas.create_oval(cx - 16, cy - 16, cx + 16, cy + 16, outline="#00ff88", width=3, fill="#00aa44")
        self.canvas.create_text(cx, cy, text=str(idx), fill="white", font=("Segoe UI", 11, "bold"))

        # Update instruction banner
        self.canvas.itemconfig(
            self.banner,
            text=f"🔄 Added Step {idx}: ({x}, {y}) | LEFT-CLICK for next step | RIGHT-CLICK or ENTER when Done"
        )

    def on_done(self, event=None):
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()
        self.callback(self.steps)

    def on_cancel(self, event=None):
        try:
            self.root.grab_release()
        except Exception:
            pass
        self.root.destroy()
        self.callback(None)


class DashboardApp:
    def __init__(self, root, engine, config_manager):
        self.root = root
        self.engine = engine
        self.cfg_mgr = config_manager
        
        self.root.title("Auto Fishing Macro - Professional Dashboard")
        self.root.geometry("860x780")
        self.root.config(bg="#181820")
        self.root.resizable(False, False)

        # Attach engine callbacks
        self.engine.log_callback = self.add_log
        self.engine.state_callback = self.update_state_badge

        self._setup_styles()
        self._build_ui()
        self._load_current_config()
        self.engine.start_hotkey_listener()

        # Update preview frame loop
        self.root.after(50, self._update_preview_loop)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure(".", background="#181820", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("TLabel", background="#181820", foreground="#ffffff")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), background="#2a2a38", foreground="#ffffff", borderwidth=0)
        style.map("TButton", background=[("active", "#3a3a4c")])

    def _build_ui(self):
        # Header Title Banner
        header = tk.Frame(self.root, bg="#20202d", height=60)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(header, text="🎣 AUTO-FISHING BOT PRO", font=("Segoe UI", 16, "bold"), bg="#20202d", fg="#00d2ff")
        title_lbl.pack(side=tk.LEFT, padx=20, pady=12)

        self.status_badge = tk.Label(header, text="STATUS: IDLE", font=("Segoe UI", 11, "bold"), bg="#333344", fg="#aaaaaa", padx=12, pady=4)
        self.status_badge.pack(side=tk.RIGHT, padx=20, pady=12)

        # Main Layout (2 Columns)
        body = tk.Frame(self.root, bg="#181820")
        body.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        left_col = tk.Frame(body, bg="#181820", width=430)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_col = tk.Frame(body, bg="#181820", width=380)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # LEFT COLUMN: Calibration & Controls
        # -------------------------------------------------------------
        # Card 1: Calibration
        card1 = tk.LabelFrame(left_col, text=" 📍 Calibration Setup ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=12, pady=10, bd=1, relief="solid")
        card1.pack(fill=tk.X, pady=(0, 10))

        # Grid of calibration buttons (2 columns)
        g_frame = tk.Frame(card1, bg="#222230")
        g_frame.pack(fill=tk.X)

        btn_cast = tk.Button(g_frame, text="🎯 1. Cast Spot", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_set_cast_spot)
        btn_cast.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 2))

        btn_roi = tk.Button(g_frame, text="📐 2. Minigame ROI", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_set_roi)
        btn_roi.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 2))

        btn_hotbar = tk.Button(g_frame, text="📦 3. Hotbar ROI", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_set_hotbar_roi)
        btn_hotbar.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 2))

        btn_trash = tk.Button(g_frame, text="🗑️ 4. Trash Button", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_set_trash_pos)
        btn_trash.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(0, 2))

        btn_timer = tk.Button(g_frame, text="⏱️ 5. Timer ROI", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_set_timer_roi)
        btn_timer.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=(0, 2))

        btn_seq = tk.Button(g_frame, text="🔄 6. Stage Sequence", font=("Segoe UI", 8, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", relief="flat", pady=4, command=self.on_manage_stage_sequence)
        btn_seq.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=(0, 2))

        g_frame.columnconfigure(0, weight=1)
        g_frame.columnconfigure(1, weight=1)

        # Status labels
        self.lbl_cast_pos = tk.Label(card1, text="Cast Spot: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_cast_pos.pack(fill=tk.X)
        self.lbl_roi_pos = tk.Label(card1, text="Minigame ROI: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_roi_pos.pack(fill=tk.X)
        self.lbl_hotbar_pos = tk.Label(card1, text="Hotbar ROI: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_hotbar_pos.pack(fill=tk.X)
        self.lbl_trash_pos = tk.Label(card1, text="Trash Button: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_trash_pos.pack(fill=tk.X)
        self.lbl_timer_pos = tk.Label(card1, text="Timer ROI: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_timer_pos.pack(fill=tk.X)
        self.lbl_seq_pos = tk.Label(card1, text="Stage Sequence: 0 steps", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_seq_pos.pack(fill=tk.X)

        # Card 2: Options & Inventory Cleanup Interval
        card_time = tk.LabelFrame(left_col, text=" ⚙️ Macro Options & Inventory Halt ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=12, pady=8, bd=1, relief="solid")
        card_time.pack(fill=tk.X, pady=(0, 10))

        # Inventory check interval entry
        inv_frame = tk.Frame(card_time, bg="#222230")
        inv_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(inv_frame, text="Halt & Clean Inventory Every N Fish:", font=("Segoe UI", 8, "bold"), bg="#222230", fg="#ffffff").pack(side=tk.LEFT)
        self.entry_inv_interval = tk.Entry(inv_frame, font=("Consolas", 10, "bold"), width=5, bg="#111118", fg="#00ff88", insertbackground="white", bd=1, relief="solid")
        self.entry_inv_interval.pack(side=tk.LEFT, padx=8)
        self.entry_inv_interval.bind("<FocusOut>", lambda e: self._on_inv_interval_change())
        self.entry_inv_interval.bind("<Return>", lambda e: self._on_inv_interval_change())

        # Time-Based Pitch Mode
        self.time_cast_var = tk.BooleanVar()
        chk_time = tk.Checkbutton(card_time, text="Enable Time-Based Pitch Mode", variable=self.time_cast_var, font=("Segoe UI", 9, "bold"), bg="#222230", fg="#ffffff", selectcolor="#181820", activebackground="#222230", activeforeground="#ffffff", command=self._on_time_cast_toggle)
        chk_time.pack(anchor="w", pady=(0, 4))

        time_frame = tk.Frame(card_time, bg="#222230")
        time_frame.pack(fill=tk.X)
        tk.Label(time_frame, text="Target Time (MM:SS):", font=("Segoe UI", 8, "bold"), bg="#222230", fg="#aaaaaa").pack(side=tk.LEFT)
        self.entry_target_time = tk.Entry(time_frame, font=("Consolas", 10, "bold"), width=8, bg="#111118", fg="#00ff88", insertbackground="white", bd=1, relief="solid")
        self.entry_target_time.pack(side=tk.LEFT, padx=8)
        self.entry_target_time.bind("<FocusOut>", lambda e: self._on_target_time_change())
        self.entry_target_time.bind("<Return>", lambda e: self._on_target_time_change())

        # Card 3: PID Sensitivity Tuning
        card3 = tk.LabelFrame(left_col, text=" ⚙️ Sensitivity & PID Controls ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=12, pady=8, bd=1, relief="solid")
        card3.pack(fill=tk.X, pady=(0, 10))

        # Kp Slider
        tk.Label(card3, text="Sensitivity (Kp - Response Force):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kp = tk.Scale(card3, from_=0.01, to=0.30, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kp.pack(fill=tk.X, pady=(0, 2))

        # Kd Slider
        tk.Label(card3, text="Damping (Kd - Momentum Stop):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kd = tk.Scale(card3, from_=0.00, to=0.20, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kd.pack(fill=tk.X, pady=(0, 2))

        # Kv Slider (Velocity Feedforward)
        tk.Label(card3, text="Velocity Gain (Kv - Predictive Burst):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kv = tk.Scale(card3, from_=0.00, to=0.10, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kv.pack(fill=tk.X, pady=(0, 2))

        # Offset Slider
        tk.Label(card3, text="Target Offset (Offset Pixel Bias):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_offset = tk.Scale(card3, from_=-30, to=30, resolution=1, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_offset.pack(fill=tk.X)

        # Action Buttons (Start / Stop)
        ctrl_frame = tk.Frame(left_col, bg="#181820")
        ctrl_frame.pack(fill=tk.X, pady=(5, 0))

        self.btn_start = tk.Button(ctrl_frame, text="▶ START (F5)", font=("Segoe UI", 11, "bold"), bg="#009944", fg="#ffffff", activebackground="#00cc55", activeforeground="#ffffff", relief="flat", pady=10, command=self.on_start_macro)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_stop = tk.Button(ctrl_frame, text="⏹ STOP (F8)", font=("Segoe UI", 11, "bold"), bg="#cc2222", fg="#ffffff", activebackground="#ff3333", activeforeground="#ffffff", relief="flat", pady=10, command=self.on_stop_macro)
        self.btn_stop.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # -------------------------------------------------------------
        # RIGHT COLUMN: Debug Preview & Activity Log
        # -------------------------------------------------------------
        # Live Tracker Preview
        preview_frame = tk.LabelFrame(right_col, text=" 👁️ Live Visual Tracker ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=10, pady=10, bd=1, relief="solid")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_canvas = tk.Canvas(preview_frame, width=350, height=140, bg="#111118", highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.create_text(175, 70, text="Tracking Preview Inactive\n(Start Macro to view live tracker)", fill="#555577", font=("Segoe UI", 10))

        # Log View
        log_frame = tk.LabelFrame(right_col, text=" 📜 Activity Log ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=10, pady=10, bd=1, relief="solid")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, bg="#111118", fg="#00eeaa", font=("Consolas", 9), state=tk.DISABLED, highlightthickness=0, bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _load_current_config(self):
        cfg = self.cfg_mgr.get()

        if cfg.get("cast_pos"):
            pos = cfg["cast_pos"]
            self.lbl_cast_pos.config(text=f"Cast Spot: X={pos[0]}, Y={pos[1]}", fg="#00ff88")

        if cfg.get("minigame_roi"):
            roi = cfg["minigame_roi"]
            w = roi[2] - roi[0]
            h = roi[3] - roi[1]
            self.lbl_roi_pos.config(text=f"Minigame ROI: ({roi[0]},{roi[1]}) -> {w}x{h}px", fg="#00ff88")

        if cfg.get("hotbar_roi"):
            roi = cfg["hotbar_roi"]
            w = roi[2] - roi[0]
            h = roi[3] - roi[1]
            self.lbl_hotbar_pos.config(text=f"Hotbar ROI: ({roi[0]},{roi[1]}) -> {w}x{h}px", fg="#00ff88")

        if cfg.get("trash_pos"):
            pos = cfg["trash_pos"]
            self.lbl_trash_pos.config(text=f"Trash Button: X={pos[0]}, Y={pos[1]}", fg="#00ff88")

        if cfg.get("timer_roi"):
            roi = cfg["timer_roi"]
            w = roi[2] - roi[0]
            h = roi[3] - roi[1]
            self.lbl_timer_pos.config(text=f"Timer ROI: ({roi[0]},{roi[1]}) -> {w}x{h}px", fg="#00ff88")

        seq = cfg.get("stage_reset_sequence", [])
        self.lbl_seq_pos.config(text=f"Stage Sequence: {len(seq)} click step(s)", fg="#00ff88" if seq else "#8888aa")

        self.entry_inv_interval.delete(0, tk.END)
        self.entry_inv_interval.insert(0, str(cfg.get("inventory_check_interval", 5)))

        self.time_cast_var.set(cfg.get("time_cast_enabled", False))
        self.entry_target_time.delete(0, tk.END)
        self.entry_target_time.insert(0, cfg.get("target_time_str", "01:00"))

        self.slider_kp.set(cfg.get("kp", 0.08))
        self.slider_kd.set(cfg.get("kd", 0.05))
        self.slider_kv.set(cfg.get("kv", 0.03))
        self.slider_offset.set(cfg.get("target_offset", 0))

        self.engine.update_pid_settings(
            cfg.get("kp", 0.08), 
            cfg.get("kd", 0.05), 
            cfg.get("kv", 0.03), 
            cfg.get("target_offset", 0)
        )

    def on_set_cast_spot(self):
        self.root.iconify()
        SpotSelectorOverlay(self._on_cast_spot_selected)

    def _on_cast_spot_selected(self, x, y):
        self.root.deiconify()
        self.cfg_mgr.set("cast_pos", [x, y])
        self.lbl_cast_pos.config(text=f"Cast Spot: X={x}, Y={y}", fg="#00ff88")
        self.add_log(f"Cast spot saved: ({x}, {y})")

    def on_set_roi(self):
        self.root.iconify()
        ROISelectorOverlay(self._on_roi_selected)

    def _on_roi_selected(self, x1, y1, x2, y2):
        self.root.deiconify()
        roi = [x1, y1, x2, y2]
        self.cfg_mgr.set("minigame_roi", roi)
        w = x2 - x1
        h = y2 - y1
        self.lbl_roi_pos.config(text=f"Minigame ROI: ({x1},{y1}) -> {w}x{h}px", fg="#00ff88")
        self.add_log(f"Minigame ROI saved: ({x1},{y1}) to ({x2},{y2}) [{w}x{h}px]")

    def on_set_hotbar_roi(self):
        self.root.iconify()
        ROISelectorOverlay(self._on_hotbar_roi_selected)

    def _on_hotbar_roi_selected(self, x1, y1, x2, y2):
        self.root.deiconify()
        roi = [x1, y1, x2, y2]
        self.cfg_mgr.set("hotbar_roi", roi)
        w = x2 - x1
        h = y2 - y1
        self.lbl_hotbar_pos.config(text=f"Hotbar ROI: ({x1},{y1}) -> {w}x{h}px", fg="#00ff88")
        self.add_log(f"Hotbar ROI saved: ({x1},{y1}) to ({x2},{y2}) [{w}x{h}px]")

    def on_set_trash_pos(self):
        self.root.iconify()
        SpotSelectorOverlay(self._on_trash_pos_selected)

    def _on_trash_pos_selected(self, x, y):
        self.root.deiconify()
        self.cfg_mgr.set("trash_pos", [x, y])
        self.lbl_trash_pos.config(text=f"Trash Button: X={x}, Y={y}", fg="#00ff88")
        self.add_log(f"Trash Button position saved: ({x}, {y})")

    def on_set_timer_roi(self):
        self.root.iconify()
        ROISelectorOverlay(self._on_timer_roi_selected)

    def _on_timer_roi_selected(self, x1, y1, x2, y2):
        self.root.deiconify()
        roi = [x1, y1, x2, y2]
        self.cfg_mgr.set("timer_roi", roi)
        w = x2 - x1
        h = y2 - y1
        self.lbl_timer_pos.config(text=f"Timer ROI: ({x1},{y1}) -> {w}x{h}px", fg="#00ff88")
        self.add_log(f"Timer ROI saved: ({x1},{y1}) to ({x2},{y2}) [{w}x{h}px]")

    def on_manage_stage_sequence(self):
        self.root.iconify()
        MultiStepSequenceOverlay(self._on_stage_sequence_selected)

    def _on_stage_sequence_selected(self, points):
        self.root.deiconify()
        if points is not None:
            if points:
                seq = [{"x": x, "y": y, "delay": 1.0} for x, y in points]
                self.cfg_mgr.set("stage_reset_sequence", seq)
                self.lbl_seq_pos.config(text=f"Stage Sequence: {len(seq)} click step(s)", fg="#00ff88")
                self.add_log(f"Stage Reset Sequence saved with {len(seq)} click step(s).")
            else:
                self.cfg_mgr.set("stage_reset_sequence", [])
                self.lbl_seq_pos.config(text="Stage Sequence: 0 steps", fg="#8888aa")
                self.add_log("Stage Reset Sequence cleared.")
        else:
            self.add_log("Stage Reset Sequence selection cancelled.")

    def _on_inv_interval_change(self):
        try:
            val = int(self.entry_inv_interval.get().strip())
            val = max(1, val)
            self.cfg_mgr.set("inventory_check_interval", val)
            self.add_log(f"Inventory Cleanup Interval saved: Halt & Clean every {val} fish.")
        except ValueError:
            pass

    def _on_time_cast_toggle(self):
        val = self.time_cast_var.get()
        self.cfg_mgr.set("time_cast_enabled", val)
        self.add_log(f"Time-Based Pitch Mode: {'ENABLED' if val else 'DISABLED'}")

    def _on_target_time_change(self):
        val = self.entry_target_time.get().strip()
        self.cfg_mgr.set("target_time_str", val)
        self.add_log(f"Target Cast Time saved: '{val}'")

    def _on_pid_slider_change(self, val):
        kp = float(self.slider_kp.get())
        kd = float(self.slider_kd.get())
        kv = float(self.slider_kv.get())
        offset = int(self.slider_offset.get())

        self.cfg_mgr.set("kp", kp)
        self.cfg_mgr.set("kd", kd)
        self.cfg_mgr.set("kv", kv)
        self.cfg_mgr.set("target_offset", offset)

        self.engine.update_pid_settings(kp, kd, kv, offset)

    def on_start_macro(self):
        self.engine.start()

    def on_stop_macro(self):
        self.engine.stop()

    def update_state_badge(self, state):
        badge_colors = {
            "STOPPED": ("STATUS: STOPPED", "#333344", "#aaaaaa"),
            "CASTING": ("STATUS: CASTING BAIT", "#886600", "#ffdd00"),
            "WAITING_FOR_UI": ("STATUS: WAITING FOR BITE", "#0066aa", "#00d2ff"),
            "PLAYING": ("STATUS: PLAYING MINIGAME", "#009944", "#00ff88"),
            "RECAST_WAIT": ("STATUS: FISH CAUGHT (WAITING)", "#660088", "#e088ff"),
            "CLEANING_INVENTORY": ("STATUS: PROCESSING HOTBAR / TOMES", "#cc0088", "#ff88ee"),
            "REPEATING_STAGE": ("STATUS: REPEATING STAGE SEQUENCE", "#0088cc", "#88e0ff")
        }
        text, bg, fg = badge_colors.get(state.value, ("STATUS: IDLE", "#333344", "#aaaaaa"))
        self.status_badge.config(text=text, bg=bg, fg=fg)

    def add_log(self, text):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{text}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_preview_loop(self):
        try:
            if not self.engine.frame_queue.empty():
                frame = self.engine.frame_queue.get_nowait()
                if frame is not None and frame.size > 0:
                    # Resize to fit preview canvas (350x140)
                    h, w = frame.shape[:2]
                    scale = min(350 / w, 140 / h)
                    nw, nh = int(w * scale), int(h * scale)
                    resized = cv2.resize(frame, (nw, nh))

                    # Convert BGR to RGB for PIL
                    rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb_frame)
                    photo = ImageTk.PhotoImage(image=img)

                    self.preview_canvas.delete("all")
                    self.preview_canvas.create_image(175, 70, image=photo, anchor=tk.CENTER)
                    self.preview_canvas.image = photo
        except Exception:
            pass

        self.root.after(40, self._update_preview_loop)
