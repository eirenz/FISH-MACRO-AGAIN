import time

class VisionTracker:
    """
    Real-time vision tracking engine using OpenCV & MSS.
    Detects Minigame UI presence, blue capture bar, fish icon position & velocity,
    hotbar capacity, and Tome items for deletion.
    """
    def __init__(self):
        self.sct = mss.mss()
        self.prev_fish_x = None
        self.prev_fish_time = time.time()
        self.fish_velocity = 0.0

    def grab_roi(self, roi):
        """
        Grab screenshot of region of interest.
        roi: tuple (x1, y1, x2, y2)
        Returns OpenCV BGR image array.
        """
        x1, y1, x2, y2 = roi
        monitor = {
            "top": int(y1),
            "left": int(x1),
            "width": int(x2 - x1),
            "height": int(y2 - y1)
        }
        sct_img = self.sct.grab(monitor)
        # Convert BGRA to BGR
        frame = np.array(sct_img)[:, :, :3]
        return frame

    def is_ui_present(self, img_bgr):
        """
        Detects if the fishing minigame bar UI is currently visible.
        Checks for characteristic blue slider bar & dark container frame pixels.
        """
        if img_bgr is None or img_bgr.size == 0:
            return False

        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        # Range for blue capture bar (HSV)
        lower_blue = np.array([90, 100, 100])
        upper_blue = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
        blue_pixels = cv2.countNonZero(blue_mask)

        # UI is present if a sufficient cluster of blue bar pixels exists
        return blue_pixels > 80

    def track(self, img_bgr):
        """
        Processes image frame and tracks Fish X, Fish Velocity, and Bar X position.
        Returns:
            fish_x (float or None)
            bar_x (float or None)
            fish_vel (float)
            debug_frame (BGR image with visual overlays)
            ui_present (bool)
        """
        if img_bgr is None or img_bgr.size == 0:
            return None, None, 0.0, None, False

        debug_frame = img_bgr.copy()
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

        # -------------------------------------------------------------
        # 1. Track Blue Capture Bar
        # -------------------------------------------------------------
        lower_blue = np.array([90, 100, 100])
        upper_blue = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        contours_blue, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        bar_x = None
        bar_w = None
        by, bh = 0, debug_frame.shape[0]

        if contours_blue:
            # Find largest blue contour (the main blue bar)
            largest_blue = max(contours_blue, key=cv2.contourArea)
            if cv2.contourArea(largest_blue) > 50:
                bx, by, bw, bh = cv2.boundingRect(largest_blue)
                bar_x = bx + bw / 2.0
                bar_w = bw
                # Draw bar overlay (Green box)
                cv2.rectangle(debug_frame, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
                cv2.line(debug_frame, (int(bar_x), by), (int(bar_x), by + bh), (0, 255, 0), 2)

        # -------------------------------------------------------------
        # 2. Track White Fish Icon (Scoped to Slider Track Y-bounds)
        # -------------------------------------------------------------
        lower_white = np.array([0, 0, 180])
        upper_white = np.array([180, 80, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)

        contours_white, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        fish_x = None
        valid_fish_contours = []
        
        # Determine track Y-bounds if blue bar was detected
        track_y1 = (by - 10) if bar_x is not None else 0
        track_y2 = (by + bh + 10) if bar_x is not None else debug_frame.shape[0]

        for c in contours_white:
            area = cv2.contourArea(c)
            # Fish icon is small to medium sized contour
            if 15 < area < 800:
                fx, fy, fw, fh = cv2.boundingRect(c)
                # Ensure contour is within the slider track Y-bounds (ignores top progress bar)
                if track_y1 <= fy <= track_y2:
                    aspect_ratio = fw / float(fh)
                    if 0.5 <= aspect_ratio <= 3.5:
                        valid_fish_contours.append((c, fx, fy, fw, fh, area))

        now = time.time()
        dt = max(now - self.prev_fish_time, 0.001)

        if valid_fish_contours:
            # Select best contour representing the fish icon
            best_fish = max(valid_fish_contours, key=lambda item: item[5])
            _, fx, fy, fw, fh, _ = best_fish
            fish_x = fx + fw / 2.0
            
            # Compute velocity
            if self.prev_fish_x is not None:
                self.fish_velocity = (fish_x - self.prev_fish_x) / dt
            self.prev_fish_x = fish_x
            self.prev_fish_time = now

            # Draw fish overlay (Red box & center point)
            cv2.rectangle(debug_frame, (fx, fy), (fx + fw, fy + fh), (0, 0, 255), 2)
            cv2.circle(debug_frame, (int(fish_x), int(fy + fh / 2)), 4, (0, 0, 255), -1)

        ui_present = (bar_x is not None)

        # Draw status text on debug frame
        if bar_x is not None and fish_x is not None:
            cv2.putText(debug_frame, f"Fish: {int(fish_x)}px  Bar: {int(bar_x)}px  Vel: {int(self.fish_velocity)}", 
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        elif ui_present:
            cv2.putText(debug_frame, "UI Detected (Searching Fish...)", 
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        return fish_x, bar_x, self.fish_velocity, debug_frame, ui_present

    def check_hotbar(self, hotbar_img):
        """
        Scans hotbar ROI image (6 slots).
        Returns:
            occupied_slots: list of indices 0..5 that contain items
            is_full: bool (True if all 6 slots are occupied)
            slot_crops: list of 6 BGR images for each slot
        """
        if hotbar_img is None or hotbar_img.size == 0:
            return [], False, []

        h, w = hotbar_img.shape[:2]
        slot_w = w / 6.0
        occupied_slots = []
        slot_crops = []

        for i in range(6):
            x1 = int(i * slot_w)
            x2 = int((i + 1) * slot_w)
            crop = hotbar_img[:, x1:x2]
            slot_crops.append(crop)

            # Analyze color variance / non-black pixels in center area of slot crop
            ch, cw = crop.shape[:2]
            center_crop = crop[int(ch * 0.15):int(ch * 0.85), int(cw * 0.15):int(cw * 0.85)]
            
            # Calculate mean brightness and color std deviation
            gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)
            std_dev = np.std(gray)
            mean_val = np.mean(gray)

            # An occupied slot has colorful icon graphics (std_dev > 15 or mean_val > 35)
            if std_dev > 15 or mean_val > 35:
                occupied_slots.append(i)

        is_full = (len(occupied_slots) == 6)
        return occupied_slots, is_full, slot_crops

    def is_tome_item(self, slot_crop):
        """
        Detects if a slot item is a TOME (purple book with gold trim & red tag).
        """
        if slot_crop is None or slot_crop.size == 0:
            return False

        hsv = cv2.cvtColor(slot_crop, cv2.COLOR_BGR2HSV)

        # 1. Purple Book Cover (HSV)
        lower_purple = np.array([120, 50, 40])
        upper_purple = np.array([165, 255, 255])
        purple_mask = cv2.inRange(hsv, lower_purple, upper_purple)
        purple_pixels = cv2.countNonZero(purple_mask)

        # 2. Red Ribbon / Tome Tag (HSV red wraps around 0 and 180)
        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 100, 100])
        upper_red2 = np.array([180, 255, 255])
        
        red_mask = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red1, upper_red1),
            cv2.inRange(hsv, lower_red2, upper_red2)
        )
        red_pixels = cv2.countNonZero(red_mask)

        # A Tome has significant purple book area (>60 pixels) AND red ribbon badge pixels (>10 pixels)
        is_tome = (purple_pixels > 60 and red_pixels > 10) or (purple_pixels > 120)
        return is_tome

    def read_timer_display(self, timer_crop):
        """
        Reads digits from the Timer ROI display (e.g. '01:11').
        Returns string 'MM:SS' or None if unreadable.
        """
        if timer_crop is None or timer_crop.size == 0:
            return None

        import re
        try:
            import pytesseract
            # Preprocess image for OCR
            gray = cv2.cvtColor(timer_crop, cv2.COLOR_BGR2GRAY)
            # Upscale 2.5x for crisp digit contours
            scaled = cv2.resize(gray, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            # Contrast thresholding
            _, thresh = cv2.threshold(scaled, 180, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

            # OCR with whitelist
            text = pytesseract.image_to_string(thresh, config='--psm 7 -c tessedit_char_whitelist=0123456789:')
            text = text.strip()

            # Find MM:SS pattern
            match = re.search(r'\d{1,2}:\d{2}', text)
            if match:
                parts = match.group(0).split(':')
                m, s = int(parts[0]), int(parts[1])
                return f"{m:02d}:{s:02d}"

            # Fallback: digits only (e.g. "0111" -> "01:11")
            digits = re.sub(r'[^\d]', '', text)
            if len(digits) == 4:
                return f"{digits[:2]}:{digits[2:]}"
            elif len(digits) == 3:
                return f"0{digits[0]}:{digits[1:]}"

        except Exception as e:
            pass

        return None


