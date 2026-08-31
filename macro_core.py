import time
import threading
import queue
from enum import Enum
import pynput.keyboard as keyboard
from tracker import VisionTracker
from controller import MouseController, PIDController

class MacroState(Enum):
    STOPPED = "STOPPED"
    CASTING = "CASTING"
    WAITING_FOR_UI = "WAITING_FOR_UI"
    PLAYING = "PLAYING"
    RECAST_WAIT = "RECAST_WAIT"
    CLEANING_INVENTORY = "CLEANING_INVENTORY"
    REPEATING_STAGE = "REPEATING_STAGE"

class AutoFishingEngine:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.tracker = VisionTracker()
        self.mouse = MouseController()
        self.pid = PIDController()

        self.state = MacroState.STOPPED
        self.running = False
        self.worker_thread = None
        self.hk_listener = None

        # Callbacks & Queues
        self.log_callback = None
        self.state_callback = None
        self.frame_queue = queue.Queue(maxsize=2)

    def log(self, message):
        print(f"[Macro] {message}")
        if self.log_callback:
            self.log_callback(message)

    def set_state(self, new_state):
        self.state = new_state
        self.log(f"State -> {new_state.value}")
        if self.state_callback:
            self.state_callback(new_state)

    def start(self):
        if self.running:
            return
        
        cfg = self.config_manager.get()
        if not cfg.get("cast_pos"):
            self.log("ERROR: Fishing spot not set! Please click 'Set Cast Spot' first.")
            return
        if not cfg.get("minigame_roi"):
            self.log("ERROR: Minigame ROI not set! Please click 'Set Minigame ROI' first.")
            return

        self.running = True
        self.set_state(MacroState.CASTING)
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.running = False
        self.mouse.force_release()
        self.set_state(MacroState.STOPPED)
        self.log("Macro Stopped.")

    def update_pid_settings(self, kp, kd, kv, target_offset):
        self.pid.kp = kp
        self.pid.kd = kd
        self.pid.kv = kv
        self.pid.target_offset = target_offset

    def _next_after_cycle(self, cfg):
        """Determines next state after minigame / inventory clean (Stage Reset vs Cast)."""
        stage_seq = cfg.get("stage_reset_sequence", [])
        if stage_seq and len(stage_seq) > 0:
            self.set_state(MacroState.REPEATING_STAGE)
        else:
            self.set_state(MacroState.CASTING)

    def _run_loop(self):
        ui_missing_count = 0
        wait_start_time = 0

        while self.running:
            cfg = self.config_manager.get()
            cast_pos = cfg.get("cast_pos")
            roi = cfg.get("minigame_roi")
            hotbar_roi = cfg.get("hotbar_roi")
            trash_pos = cfg.get("trash_pos")
            timer_roi = cfg.get("timer_roi")
            time_cast_enabled = cfg.get("time_cast_enabled", False)
            target_time_str = cfg.get("target_time_str", "01:00")
            stage_seq = cfg.get("stage_reset_sequence", [])

            # ---------------------------------------------------------
            # STATE: CASTING
            # ---------------------------------------------------------
            if self.state == MacroState.CASTING:
                if time_cast_enabled and timer_roi:
                    self.log(f"⏱️ Time-Based Pitch Mode active. Waiting for timer to match '{target_time_str}'...")
                    matched = False
                    while self.running and not matched:
                        timer_crop = self.tracker.grab_roi(timer_roi)
                        curr_time = self.tracker.read_timer_display(timer_crop)
                        if curr_time:
                            self.log(f"Timer reading: {curr_time} (Target: {target_time_str})")
                            if curr_time == target_time_str:
                                self.log(f"🎯 Target time '{target_time_str}' reached! Throwing bait now!")
                                matched = True
                                break
                        time.sleep(0.2)

                self.log("Starting bait casting...")
                self.mouse.click_at(cast_pos[0], cast_pos[1])
                wait_start_time = time.time()
                last_spam_click = time.time()
                self.set_state(MacroState.WAITING_FOR_UI)

            # ---------------------------------------------------------
            # STATE: WAITING FOR MINIGAME UI (Continuous M1 Click Spam)
            # ---------------------------------------------------------
            # ---------------------------------------------------------
            # STATE: WAITING FOR MINIGAME UI (Fast Continuous M1 Click Spam)
            # ---------------------------------------------------------
            elif self.state == MacroState.WAITING_FOR_UI:
                frame = self.tracker.grab_roi(roi)
                ui_present = self.tracker.is_ui_present(frame)

                if ui_present:
                    self.log("🎯 MINIGAME UI DETECTED! STOPPING M1 CLICK SPAM & STARTING MINIGAME...")
                    self.mouse.force_release()
                    ui_missing_count = 0
                    self.pid.prev_error = 0.0
                    self.pid.prev_time = time.time()
                    self.set_state(MacroState.PLAYING)
                else:
                    # Fast continuous M1 spam click every 0.15s until UI appears
                    now = time.time()
                    if now - last_spam_click > 0.15:
                        self.mouse.click_at(cast_pos[0], cast_pos[1])
                        last_spam_click = now

                    # Safety timeout: recast setup after 30s
                    if time.time() - wait_start_time > 30.0:
                        self.log("No minigame UI after timeout. Restarting cast cycle...")
                        self.set_state(MacroState.CASTING)
                    else:
                        time.sleep(0.015)

            # ---------------------------------------------------------
            # STATE: PLAYING MINIGAME
            # ---------------------------------------------------------
            elif self.state == MacroState.PLAYING:
                frame = self.tracker.grab_roi(roi)
                fish_x, bar_x, fish_vel, debug_frame, ui_present = self.tracker.track(frame)

                # Send frame to GUI preview
                if debug_frame is not None:
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put(debug_frame)

                if ui_present and bar_x is not None:
                    ui_missing_count = 0
                    
                    if fish_x is not None:
                        # Update PID with velocity feedforward
                        should_press, err, u = self.pid.update(fish_x, bar_x, fish_vel)
                        if should_press:
                            self.mouse.press()
                        else:
                            self.mouse.release()
                    else:
                        # Fish icon temporarily unreadable -> release mouse button
                        self.mouse.release()
                else:
                    ui_missing_count += 1
                    # If UI missing for 4 consecutive frames (~50-80ms), minigame ended
                    if ui_missing_count > 4:
                        self.mouse.force_release()
                        self.log("⏹️ Minigame Complete / Caught Fish! Halting fishing cycle for inventory check...")
                        self.set_state(MacroState.RECAST_WAIT)

                time.sleep(0.005) # ~120-200 FPS tracking loop

            # ---------------------------------------------------------
            # STATE: RECAST WAIT & INVENTORY CHECK (HALTS FISHING CYCLE)
            # ---------------------------------------------------------
            elif self.state == MacroState.RECAST_WAIT:
                self.mouse.force_release()
                recast_delay = min(cfg.get("recast_delay", 0.4), 0.5)
                time.sleep(recast_delay)

                if hotbar_roi:
                    self.log("📦 Halting fishing cycle: Starting Hotbar Key Pressing & Tome Deletion...")
                    self.set_state(MacroState.CLEANING_INVENTORY)
                else:
                    self.log("Hotbar ROI not calibrated! Resuming fishing cycle...")
                    self._next_after_cycle(cfg)

            # ---------------------------------------------------------
            # STATE: CLEANING INVENTORY (Press 1..6 Keys & Drag Tomes to Trash)
            # ---------------------------------------------------------
            elif self.state == MacroState.CLEANING_INVENTORY:
                self.log("📦 Hotbar Processing: Pressing keys 1, 2, 3, 4, 5, 6...")
                
                # 1. Press hotbar keys 1, 2, 3, 4, 5, 6 sequentially
                for slot_num in range(1, 7):
                    if not self.running:
                        break
                    self.log(f"Pressing hotbar key '{slot_num}'...")
                    self.mouse.press_number_key(str(slot_num))
                    time.sleep(0.12)

                time.sleep(0.2)

                # 2. Check remaining items for TOME and INSTANTLY DRAG Tomes to Trash Can button
                if hotbar_roi and trash_pos:
                    hotbar_img = self.tracker.grab_roi(hotbar_roi)
                    occupied_slots, is_full, slot_crops = self.tracker.check_hotbar(hotbar_img)
                    
                    hx1, hy1, hx2, hy2 = hotbar_roi
                    slot_w = (hx2 - hx1) / 6.0
                    slot_y_center = (hy1 + hy2) / 2.0

                    for i in range(len(slot_crops)):
                        if not self.running:
                            break

                        slot_crop = slot_crops[i]
                        is_tome, detected_info = self.tracker.is_tome_item(slot_crop)
                        if is_tome:
                            slot_x_center = hx1 + (i + 0.5) * slot_w
                            self.log(f"📜 TOME DETECTED in Slot {i+1} ({detected_info})! INSTANTLY DRAGGING TO TRASH BUTTON...")
                            self.mouse.drag_and_drop((slot_x_center, slot_y_center), trash_pos, duration=0.25)
                            time.sleep(0.2)
                        else:
                            self.log(f"Slot {i+1}: Non-Tome item ({detected_info}). Kept in hotbar.")
                elif not trash_pos:
                    self.log("⚠️ Trash Can button not calibrated! Skipping Tome deletion.")

                self.log("⚡ Inventory cleanup finished! Resuming fishing cycle...")
                self._next_after_cycle(cfg)

            # ---------------------------------------------------------
            # STATE: REPEATING STAGE (Executing Post-Minigame Click Sequence)
            # ---------------------------------------------------------
            elif self.state == MacroState.REPEATING_STAGE:
                if not stage_seq:
                    self.set_state(MacroState.CASTING)
                    continue

                self.log(f"🔄 Executing Stage Reset Sequence ({len(stage_seq)} steps)...")
                for idx, step in enumerate(stage_seq):
                    if not self.running:
                        break
                    sx, sy = step["x"], step["y"]
                    sdelay = step.get("delay", 1.0)
                    self.log(f"Stage Reset Step {idx+1}/{len(stage_seq)}: Clicking ({sx}, {sy}), waiting {sdelay}s...")
                    self.mouse.click_at(sx, sy)
                    time.sleep(sdelay)

                self.set_state(MacroState.CASTING)

        self.mouse.force_release()

    def start_hotkey_listener(self):
        """Listen for global F5 (start/toggle) and F8 (stop)."""
        def on_press(key):
            try:
                if key == keyboard.Key.f5:
                    if self.running:
                        self.log("Hotkey F5: Stopping macro.")
                        self.stop()
                    else:
                        self.log("Hotkey F5: Starting macro.")
                        self.start()
                elif key == keyboard.Key.f8:
                    self.log("Hotkey F8: Emergency Stop.")
                    self.stop()
            except Exception as e:
                print(f"Hotkey Error: {e}")

        self.hk_listener = keyboard.Listener(on_press=on_press)
        self.hk_listener.daemon = True
        self.hk_listener.start()
