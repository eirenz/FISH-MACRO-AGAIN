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
    """Full-screen overlay to select cast coordinates."""
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.3)
        self.root.attributes("-topmost", True)
        self.root.config(bg="gray")
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Instruction text
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text="🎯 LEFT-CLICK anywhere to set the Fishing Cast Spot (Press ESC to cancel)",
            fill="white",
            font=("Segoe UI", 16, "bold")
        )

        self.root.bind("<Button-1>", self.on_click)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_click(self, event):
        x, y = event.x_root, event.y_root
        self.root.destroy()
        self.callback(x, y)


class ROISelectorOverlay:
    """Full-screen overlay to select minigame region of interest (ROI)."""
    def __init__(self, callback):
        self.callback = callback
        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.3)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Banner
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text="📐 CLICK & DRAG to select the Minigame Bar Region (Press ESC to cancel)",
            fill="cyan",
            font=("Segoe UI", 16, "bold")
        )

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.root.bind("<ButtonPress-1>", self.on_press)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

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
        self.root.destroy()
        
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        if (x2 - x1) > 20 and (y2 - y1) > 10:
            self.callback(x1, y1, x2, y2)


class DashboardApp:
    def __init__(self, root, engine, config_manager):
        self.root = root
        self.engine = engine
        self.cfg_mgr = config_manager
        
        self.root.title("Auto Fishing Macro - Professional Dashboard")
        self.root.geometry("840x740")
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

        left_col = tk.Frame(body, bg="#181820", width=420)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_col = tk.Frame(body, bg="#181820", width=380)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # LEFT COLUMN: Calibration & Control
        # -------------------------------------------------------------
        # Card 1: Calibration
        card1 = tk.LabelFrame(left_col, text=" 📍 Calibration Setup ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=12, pady=12, bd=1, relief="solid")
        card1.pack(fill=tk.X, pady=(0, 10))

        # 1. Cast spot
        btn_cast = tk.Button(card1, text="🎯 1. Set Cast Spot", font=("Segoe UI", 9, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", activeforeground="#ffffff", relief="flat", pady=4, command=self.on_set_cast_spot)
        btn_cast.pack(fill=tk.X, pady=(0, 2))
        self.lbl_cast_pos = tk.Label(card1, text="Cast Spot: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_cast_pos.pack(fill=tk.X, pady=(0, 6))

        # 2. Minigame ROI
        btn_roi = tk.Button(card1, text="📐 2. Set Minigame ROI", font=("Segoe UI", 9, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", activeforeground="#ffffff", relief="flat", pady=4, command=self.on_set_roi)
        btn_roi.pack(fill=tk.X, pady=(0, 2))
        self.lbl_roi_pos = tk.Label(card1, text="Minigame ROI: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_roi_pos.pack(fill=tk.X, pady=(0, 6))

        # 3. Hotbar ROI
        btn_hotbar = tk.Button(card1, text="📦 3. Set Hotbar ROI (Slots 1-6)", font=("Segoe UI", 9, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", activeforeground="#ffffff", relief="flat", pady=4, command=self.on_set_hotbar_roi)
        btn_hotbar.pack(fill=tk.X, pady=(0, 2))
        self.lbl_hotbar_pos = tk.Label(card1, text="Hotbar ROI: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_hotbar_pos.pack(fill=tk.X, pady=(0, 6))

        # 4. Trash Can button
        btn_trash = tk.Button(card1, text="🗑️ 4. Set Trash Button", font=("Segoe UI", 9, "bold"), bg="#2b2b40", fg="#ffffff", activebackground="#3d3d5c", activeforeground="#ffffff", relief="flat", pady=4, command=self.on_set_trash_pos)
        btn_trash.pack(fill=tk.X, pady=(0, 2))
        self.lbl_trash_pos = tk.Label(card1, text="Trash Button: Not Set", font=("Segoe UI", 8), bg="#222230", fg="#8888aa", anchor="w")
        self.lbl_trash_pos.pack(fill=tk.X)

        # Card 2: PID Sensitivity Tuning
        card2 = tk.LabelFrame(left_col, text=" ⚙️ Sensitivity & PID Controls ", font=("Segoe UI", 11, "bold"), bg="#222230", fg="#00d2ff", padx=12, pady=10, bd=1, relief="solid")
        card2.pack(fill=tk.X, pady=(0, 10))

        # Kp Slider
        tk.Label(card2, text="Sensitivity (Kp - Response Force):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kp = tk.Scale(card2, from_=0.01, to=0.30, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kp.pack(fill=tk.X, pady=(0, 4))

        # Kd Slider
        tk.Label(card2, text="Damping (Kd - Momentum Stop):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kd = tk.Scale(card2, from_=0.00, to=0.20, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kd.pack(fill=tk.X, pady=(0, 4))

        # Kv Slider (Velocity Feedforward)
        tk.Label(card2, text="Velocity Gain (Kv - Predictive Burst):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_kv = tk.Scale(card2, from_=0.00, to=0.10, resolution=0.01, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
        self.slider_kv.pack(fill=tk.X, pady=(0, 4))

        # Offset Slider
        tk.Label(card2, text="Target Offset (Offset Pixel Bias):", bg="#222230", fg="#ffffff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.slider_offset = tk.Scale(card2, from_=-30, to=30, resolution=1, orient=tk.HORIZONTAL, bg="#222230", fg="#00d2ff", highlightthickness=0, command=self._on_pid_slider_change)
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
            "CLEANING_INVENTORY": ("STATUS: PROCESSING HOTBAR / TOMES", "#cc0088", "#ff88ee")
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
