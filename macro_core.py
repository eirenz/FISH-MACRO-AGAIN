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

    def _run_loop(self):
        ui_missing_count = 0
        wait_start_time = 0

        while self.running:
            cfg = self.config_manager.get()
            cast_pos = cfg.get("cast_pos")
            roi = cfg.get("minigame_roi")
            hotbar_roi = cfg.get("hotbar_roi")
            trash_pos = cfg.get("trash_pos")

            # ---------------------------------------------------------
            # STATE: CASTING
            # ---------------------------------------------------------
            if self.state == MacroState.CASTING:
                self.log("Starting bait casting...")
                self.mouse.click_at(cast_pos[0], cast_pos[1])
                wait_start_time = time.time()
                last_spam_click = time.time()
                self.set_state(MacroState.WAITING_FOR_UI)

            # ---------------------------------------------------------
            # STATE: WAITING FOR MINIGAME UI (Continuous M1 Click Spam)
            # ---------------------------------------------------------
            elif self.state == MacroState.WAITING_FOR_UI:
                frame = self.tracker.grab_roi(roi)
                ui_present = self.tracker.is_ui_present(frame)

                if ui_present:
                    self.log("Minigame UI Detected! Starting minigame...")
                    self.mouse.force_release()
                    ui_missing_count = 0
                    self.pid.prev_error = 0.0
                    self.pid.prev_time = time.time()
                    self.set_state(MacroState.PLAYING)
                else:
                    # Periodically spam click M1 at cast spot every 0.35s
                    now = time.time()
                    if now - last_spam_click > 0.35:
                        self.mouse.click_at(cast_pos[0], cast_pos[1])
                        last_spam_click = now

                    # Safety timeout: recast setup after 30s
                    if time.time() - wait_start_time > 30.0:
                        self.log("No minigame UI after timeout. Restarting cast cycle...")
                        self.set_state(MacroState.CASTING)
                    else:
                        time.sleep(0.03)

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
                    # If UI missing for 6 consecutive frames (~80-150ms), minigame ended
                    if ui_missing_count > 6:
                        self.mouse.force_release()
                        self.log("Minigame complete / caught fish!")
                        self.set_state(MacroState.RECAST_WAIT)

                time.sleep(0.005) # ~120-200 FPS tracking loop

            # ---------------------------------------------------------
            # STATE: RECAST WAIT & INVENTORY CHECK
            # ---------------------------------------------------------
            elif self.state == MacroState.RECAST_WAIT:
                self.mouse.force_release()
                recast_delay = cfg.get("recast_delay", 1.5)
                self.log(f"Waiting {recast_delay}s before checking hotbar...")
                time.sleep(recast_delay)

                if hotbar_roi:
                    hotbar_img = self.tracker.grab_roi(hotbar_roi)
                    occupied_slots, is_full, _ = self.tracker.check_hotbar(hotbar_img)
                    if is_full:
                        self.log("🔥 HOTBAR IS FULL! Starting hotbar item processing...")
                        self.set_state(MacroState.CLEANING_INVENTORY)
                    elif occupied_slots:
                        self.log(f"Hotbar has items in slots: {[s+1 for s in occupied_slots]}. Processing...")
                        self.set_state(MacroState.CLEANING_INVENTORY)
                    else:
                        self.set_state(MacroState.CASTING)
                else:
                    self.set_state(MacroState.CASTING)

            # ---------------------------------------------------------
            # STATE: CLEANING INVENTORY (Double Click Items & Delete Tomes)
            # ---------------------------------------------------------
            elif self.state == MacroState.CLEANING_INVENTORY:
                if not hotbar_roi:
                    self.log("Hotbar ROI not calibrated! Skipping inventory check.")
                    self.set_state(MacroState.CASTING)
                    continue

                hotbar_img = self.tracker.grab_roi(hotbar_roi)
                occupied_slots, is_full, slot_crops = self.tracker.check_hotbar(hotbar_img)
                
                hx1, hy1, hx2, hy2 = hotbar_roi
                slot_w = (hx2 - hx1) / 6.0
                slot_y_center = (hy1 + hy2) / 2.0

                for i in occupied_slots:
                    if not self.running:
                        break

                    slot_x_center = hx1 + (i + 0.5) * slot_w
                    slot_crop = slot_crops[i]

                    self.log(f"Processing Hotbar Slot {i+1}...")

                    # RULE 1: Double click every item in the hotbar twice
                    self.mouse.click_at(slot_x_center, slot_y_center)
                    time.sleep(0.12)
                    self.mouse.click_at(slot_x_center, slot_y_center)
                    time.sleep(0.2)

                    # RULE 2: Check if item is a TOME
                    if self.tracker.is_tome_item(slot_crop):
                        if trash_pos:
                            self.log(f"📜 TOME detected in Slot {i+1}! Dragging to Trash Can button...")
                            self.mouse.drag_and_drop((slot_x_center, slot_y_center), trash_pos)
                            time.sleep(0.3)
                        else:
                            self.log(f"📜 TOME detected in Slot {i+1}, but Trash Can button is not calibrated!")
                    else:
                        self.log(f"Slot {i+1} item processed (Non-Tome).")

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
