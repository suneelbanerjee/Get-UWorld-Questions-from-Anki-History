# -*- coding: utf-8 -*-
import os
import time
import re
import random
from datetime import datetime
from aqt import mw
from aqt.qt import *
from aqt.utils import showText, tooltip

# Global reference to keep the window alive (Modeless)
history_window = None

# ============================================================
# 1) FILE I/O HELPERS
# ============================================================
def get_local_data_dir():
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(addon_dir, "user_data")
    if not os.path.exists(data_dir):
        try: os.makedirs(data_dir)
        except: pass
    return data_dir

def load_correct_ids_from_helper():
    try:
        addons_dir = mw.addonManager.addonsFolder()
        target_path = os.path.join(addons_dir, "UWorld_Helper", "user_data", "correct_questions.txt")
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
                return set(x.strip() for x in content.split(",") if x.strip().isdigit())
    except: pass
    return set()

def load_invalid_ids():
    data_dir = get_local_data_dir()
    path = os.path.join(data_dir, "invalid_questions.txt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return set(x.strip() for x in content.split(",") if x.strip().isdigit())
        except: pass
    return set()

def save_invalid_ids(new_bad_ids):
    if not new_bad_ids: return
    data_dir = get_local_data_dir()
    path = os.path.join(data_dir, "invalid_questions.txt")
    current_set = load_invalid_ids()
    current_set.update(new_bad_ids)
    try:
        sorted_list = sorted(list(current_set), key=lambda x: int(x))
        with open(path, "w", encoding="utf-8") as f:
            f.write(", ".join(sorted_list))
    except Exception as e:
        print(f"Error saving invalid IDs: {e}")

# ============================================================
# 2) THE UNIFIED DASHBOARD WINDOW
# ============================================================
class UWorldHistoryFetcher(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Get UWorld IDs from History")
        self.setMinimumSize(580, 780)
        
        # State Data
        self.all_found_ids = []  # Stores the final ordered list
        self.displayed_ids = []  # Stores just the batch currently shown
        
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout()

        # --- SECTION 1: SETTINGS ---
        settings_group = QGroupBox("Search Settings")
        settings_layout = QVBoxLayout()
        
        # 1. Timeframe Selection
        time_group_layout = QVBoxLayout()
        
        # Option A: Today
        self.radio_today = QRadioButton("Reviewed Today")
        self.radio_today.setChecked(True)
        time_group_layout.addWidget(self.radio_today)
        
        # Option B: Last X Hours
        hbox_hours = QHBoxLayout()
        self.radio_hours = QRadioButton("Last:")
        self.spin_hours = QSpinBox()
        self.spin_hours.setRange(1, 1000)
        self.spin_hours.setValue(4)
        self.spin_hours.setSuffix(" hours")
        hbox_hours.addWidget(self.radio_hours)
        hbox_hours.addWidget(self.spin_hours)
        hbox_hours.addStretch()
        time_group_layout.addLayout(hbox_hours)
        
        # Option C: Date Range
        hbox_range = QHBoxLayout()
        self.radio_range = QRadioButton("Between:")
        
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("MM/dd HH:mm")
        
        self.dt_end = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat("MM/dd HH:mm")
        
        hbox_range.addWidget(self.radio_range)
        hbox_range.addWidget(self.dt_start)
        hbox_range.addWidget(QLabel("to"))
        hbox_range.addWidget(self.dt_end)
        hbox_range.addStretch()
        time_group_layout.addLayout(hbox_range)
        
        settings_layout.addLayout(time_group_layout)
        
        # Divider line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        settings_layout.addWidget(line)
        
        # 2. Card States (Grid)
        checks_layout = QGridLayout()
        self.chk_learning = QCheckBox("Learning")
        self.chk_learning.setChecked(True)
        self.chk_young = QCheckBox("Young")
        self.chk_young.setChecked(True)
        self.chk_mature = QCheckBox("Mature")
        self.chk_mature.setChecked(True)
        
        checks_layout.addWidget(self.chk_learning, 0, 0)
        checks_layout.addWidget(self.chk_young, 0, 1)
        checks_layout.addWidget(self.chk_mature, 0, 2)
        
        settings_layout.addLayout(checks_layout)

        # 3. Horizontal Search & Mixing
        h_search_group = QGroupBox("Horizontal Search (Tree Search)")
        h_search_layout = QGridLayout()
        
        self.chk_horizontal = QCheckBox("Enable Tree Search")
        self.chk_horizontal.setToolTip(
            "Finds cards related to your reviews by shared UWorld tags.\n"
            "Enable to broaden your search to related concepts."
        )
        self.chk_horizontal.stateChanged.connect(self.toggle_horizontal_controls)
        
        # Layers Control
        self.lbl_depth = QLabel("Layers:")
        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(1, 5)
        self.spin_depth.setValue(1)
        self.spin_depth.setToolTip("Degrees of Separation (1 = Friends, 2 = Friends of Friends)")
        
        # Mix Percentage
        self.lbl_mix = QLabel("Batch Share:")
        self.spin_mix = QSpinBox()
        self.spin_mix.setRange(0, 100)
        self.spin_mix.setValue(50)
        self.spin_mix.setSuffix("%")
        self.spin_mix.setToolTip(
            "Percentage of the final batch allocated to Horizontal/Related questions.\n"
            "Example: 50% means half your test will be direct history, half will be related."
        )
        
        h_search_layout.addWidget(self.chk_horizontal, 0, 0, 1, 2)
        h_search_layout.addWidget(self.lbl_depth, 1, 0)
        h_search_layout.addWidget(self.spin_depth, 1, 1)
        h_search_layout.addWidget(self.lbl_mix, 1, 2)
        h_search_layout.addWidget(self.spin_mix, 1, 3)
        
        h_search_group.setLayout(h_search_layout)
        settings_layout.addWidget(h_search_group)

        # 4. Final Output Settings
        out_layout = QGridLayout()
        
        # Row 0: Batch Size & Randomize
        out_layout.addWidget(QLabel("Batch Size:"), 0, 0)
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 1000)
        self.spin_limit.setValue(40) 
        out_layout.addWidget(self.spin_limit, 0, 1)

        self.chk_randomize = QCheckBox("Randomize Order")
        self.chk_randomize.setChecked(True)
        self.chk_randomize.setToolTip("Shuffle history and horizontal questions together.")
        out_layout.addWidget(self.chk_randomize, 0, 2)
        
        # Row 1: Refill & Include Correct
        self.chk_refill = QCheckBox("Refill after filtering")
        self.chk_refill.setChecked(False) # [CHANGED] Default to Unchecked
        self.chk_refill.setToolTip(
            "If Checked: Automatically adds new questions to replace invalid ones you remove.\n"
            "If Unchecked: Removing invalid questions reduces the list size."
        )
        out_layout.addWidget(self.chk_refill, 1, 0, 1, 2) 

        self.chk_include_correct = QCheckBox("Include Correct")
        self.chk_include_correct.setToolTip("Include questions you already mastered in UWorld Helper.")
        out_layout.addWidget(self.chk_include_correct, 1, 2)
        
        settings_layout.addLayout(out_layout)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # --- SECTION 2: ACTION BUTTON ---
        self.btn_generate = QPushButton("Generate Question List")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setStyleSheet("font-weight: bold; padding: 8px; font-size: 14px;")
        self.btn_generate.clicked.connect(self.run_search)
        main_layout.addWidget(self.btn_generate)

        # --- SECTION 3: OUTPUT ---
        self.lbl_status = QLabel("Ready to search.")
        self.lbl_status.setStyleSheet("color: gray; font-style: italic; margin-top: 5px;")
        main_layout.addWidget(self.lbl_status)

        self.text_area = QTextEdit()
        self.text_area.setPlaceholderText("Questions will appear here...")
        main_layout.addWidget(self.text_area)

        # --- SECTION 4: FILTERING ---
        filter_hbox = QHBoxLayout()
        self.btn_filter = QPushButton("Remove Bad IDs from Error...")
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        self.btn_filter.setToolTip("Paste a UWorld error message here to permanently block those IDs.")
        
        self.btn_copy = QPushButton("Copy to Clipboard")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        
        filter_hbox.addWidget(self.btn_filter)
        filter_hbox.addStretch()
        filter_hbox.addWidget(self.btn_copy)
        main_layout.addLayout(filter_hbox)

        self.setLayout(main_layout)
        
        # Initial State
        self.toggle_horizontal_controls()

    def toggle_horizontal_controls(self):
        enabled = self.chk_horizontal.isChecked()
        self.spin_depth.setEnabled(enabled)
        self.lbl_depth.setEnabled(enabled)
        self.spin_mix.setEnabled(enabled)
        self.lbl_mix.setEnabled(enabled)

    # ================= LOGIC =================

    def run_search(self):
        # 1. Get Settings
        if self.radio_today.isChecked():
            start_ms = (mw.col.sched.day_cutoff - 86400) * 1000
            end_ms = time.time() * 1000 
        elif self.radio_hours.isChecked():
            start_ms = (time.time() - (self.spin_hours.value() * 3600)) * 1000
            end_ms = time.time() * 1000
        else:
            start_ms = self.dt_start.dateTime().toMSecsSinceEpoch()
            end_ms = self.dt_end.dateTime().toMSecsSinceEpoch()

        states = {
            "learning": self.chk_learning.isChecked(),
            "young": self.chk_young.isChecked(),
            "mature": self.chk_mature.isChecked()
        }
        
        horizontal_mode = self.chk_horizontal.isChecked()
        depth = self.spin_depth.value()
        mix_percent = self.spin_mix.value()
        batch_size = self.spin_limit.value()
        include_correct = self.chk_include_correct.isChecked()
        randomize = self.chk_randomize.isChecked()

        # 2. Find IDs (Split into Direct and Horizontal sets)
        direct_ids, horizontal_ids = self.find_ids_logic((start_ms, end_ms), states, horizontal_mode, depth)
        
        # 3. Filtering (Correct & Invalid)
        correct_ids = set()
        if not include_correct:
            correct_ids = load_correct_ids_from_helper()
            
        invalid_ids = load_invalid_ids()
        
        # Helper to filter a set
        def filter_set(id_set):
            valid = id_set - invalid_ids
            if not include_correct:
                valid = valid - correct_ids
            return list(valid)

        filtered_direct = filter_set(direct_ids)
        filtered_horizontal = filter_set(horizontal_ids)
        
        stats = {
            'found': len(filtered_direct) + len(filtered_horizontal),
            'removed_correct': (len(direct_ids) + len(horizontal_ids)) - (len(filtered_direct) + len(filtered_horizontal) + len(invalid_ids & (direct_ids | horizontal_ids))),
            'removed_invalid': len(invalid_ids & (direct_ids | horizontal_ids))
        }

        # 4. Mixing & Selection Logic
        final_list = []
        
        if horizontal_mode:
            # Calculate targets
            target_h = int(batch_size * (mix_percent / 100))
            target_d = batch_size - target_h
            
            # Shuffle matched pools if randomize is on (to pick random representatives)
            # If randomize is OFF, we sort to be deterministic
            if randomize:
                random.shuffle(filtered_direct)
                random.shuffle(filtered_horizontal)
            else:
                filtered_direct.sort(key=int)
                filtered_horizontal.sort(key=int)
            
            # Select Primary
            selected_d = filtered_direct[:target_d]
            selected_h = filtered_horizontal[:target_h]
            
            # Fill gaps? (Smart Fill)
            # If we didn't get enough direct, fill with more horizontal
            needed_d = target_d - len(selected_d)
            if needed_d > 0:
                extra_h = filtered_horizontal[target_h : target_h + needed_d]
                selected_h.extend(extra_h)
                
            # If we didn't get enough horizontal, fill with more direct
            needed_h = target_h - len(selected_h)
            if needed_h > 0:
                extra_d = filtered_direct[target_d : target_d + needed_h]
                selected_d.extend(extra_d)
            
            final_list = selected_d + selected_h
            
            # Add remaining overflow to the end (undisplayed but available)
            remaining_d = filtered_direct[len(selected_d):]
            remaining_h = filtered_horizontal[len(selected_h):]
            overflow = remaining_d + remaining_h
            if randomize: random.shuffle(overflow)
            
        else:
            # Pure Direct Mode
            final_list = filtered_direct
            overflow = []

        # 5. Final Randomization
        if randomize:
            random.shuffle(final_list)
        else:
            final_list.sort(key=lambda x: int(x))

        # Store full list (The active batch + any overflow)
        self.all_found_ids = final_list + (overflow if horizontal_mode else [])
        
        self.refresh_display(update_timestamp=True, stats=stats)


    def find_ids_logic(self, time_range, states, horizontal_mode, depth=1):
        start_ms, end_ms = time_range
        
        # 1. Identify Reviewed Cards
        query = f"SELECT DISTINCT cid FROM revlog WHERE id >= {int(start_ms)} AND id <= {int(end_ms)}"
        card_ids = mw.col.db.list(query)
        if not card_ids: return set(), set()

        # 2. Filter by State
        seed_nids = set()
        for cid in card_ids:
            try:
                c = mw.col.get_card(cid)
                is_learning = c.queue in (1, 3)
                is_review = c.queue == 2
                is_young = is_review and c.ivl < 21
                is_mature = is_review and c.ivl >= 21
                
                keep = False
                if is_learning and states['learning']: keep = True
                elif is_young and states['young']: keep = True
                elif is_mature and states['mature']: keep = True
                
                if keep: seed_nids.add(c.nid)
            except: continue
        
        if not seed_nids: return set(), set()

        # 3. Extract Direct UWorld IDs
        seed_uworld_ids = set()
        tag_regex = re.compile(r"(?i)UWorld.*::Step.*::(\d+)$")

        for nid in seed_nids:
            try:
                note = mw.col.get_note(nid)
                for tag in note.tags:
                    match = tag_regex.search(tag)
                    if match: seed_uworld_ids.add(match.group(1))
            except: continue

        # 4. Horizontal Expansion
        horizontal_ids = set()
        
        if horizontal_mode and seed_uworld_ids:
            current_layer_ids = set(seed_uworld_ids)
            seen_ids = set(seed_uworld_ids) # Track everything we've seen
            
            for layer in range(depth):
                if not current_layer_ids: break
                
                next_layer_nids = set()
                # Find notes sharing tags
                for qid in current_layer_ids:
                    ids_notes = mw.col.find_notes(f"tag:*UWorld*Step*::{qid}")
                    next_layer_nids.update(ids_notes)
                
                found_in_layer = set()
                for nid in next_layer_nids:
                    try:
                        note = mw.col.get_note(nid)
                        for tag in note.tags:
                            match = tag_regex.search(tag)
                            if match: found_in_layer.add(match.group(1))
                    except: continue
                
                # New IDs only
                new_ids = found_in_layer - seen_ids
                
                if not new_ids: break
                
                horizontal_ids.update(new_ids)
                seen_ids.update(new_ids)
                current_layer_ids = new_ids # Advance frontier
            
        return seed_uworld_ids, horizontal_ids

    def refresh_display(self, update_timestamp=False, stats=None):
        limit = self.spin_limit.value()
        
        # Slice
        self.displayed_ids = self.all_found_ids[:limit]
        
        # Display
        if self.displayed_ids:
            self.text_area.setPlainText(", ".join(self.displayed_ids))
        else:
            self.text_area.setPlainText("No IDs found matching criteria.")

        # Status
        if update_timestamp:
            t_str = datetime.now().strftime("%I:%M %p")
            count = len(self.displayed_ids) 
            total = len(self.all_found_ids)
            
            msg = f"Generated at {t_str}. Batch contains {count} IDs."
            if total > count:
                msg += f" (Selected from {total} matching candidates)"
                
            self.lbl_status.setText(msg)
        else:
            count = len(self.all_found_ids)
            self.lbl_status.setText(f"List updated. {count} valid IDs remaining.")

    def open_filter_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, "Paste Error List", 
            "Paste the full error message from UWorld here:")
        if ok and text:
            self.remove_ids(text)

    def remove_ids(self, error_text):
        bad_ids = set(re.findall(r'\d+', error_text))
        if not bad_ids:
            tooltip("No numbers found.")
            return

        save_invalid_ids(bad_ids)
        
        # 1. Check if we need to shrink the batch size (Refill OFF)
        displayed_set = set(self.displayed_ids)
        removed_from_display_count = len(bad_ids & displayed_set)
        
        if not self.chk_refill.isChecked() and removed_from_display_count > 0:
            current_limit = self.spin_limit.value()
            new_limit = max(0, current_limit - removed_from_display_count)
            self.spin_limit.setValue(new_limit)

        # 2. Filter Master List
        original_total = len(self.all_found_ids)
        self.all_found_ids = [x for x in self.all_found_ids if x not in bad_ids]
        total_removed = original_total - len(self.all_found_ids)
        
        # 3. Refresh
        if total_removed > 0:
            self.refresh_display()
            if self.chk_refill.isChecked():
                tooltip(f"Removed {total_removed} IDs and refilled list.")
            else:
                tooltip(f"Removed {total_removed} IDs (List shrunk by {removed_from_display_count}).")
        else:
            tooltip("No IDs found to remove.")

    def copy_to_clipboard(self):
        mw.app.clipboard().setText(self.text_area.toPlainText())
        tooltip("Copied!")

# ============================================================
# 3) ENTRY POINT
# ============================================================
def run_uworld_fetcher():
    global history_window
    if not history_window:
        history_window = UWorldHistoryFetcher(mw)
    history_window.show()
    history_window.raise_()
    history_window.activateWindow()

action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)