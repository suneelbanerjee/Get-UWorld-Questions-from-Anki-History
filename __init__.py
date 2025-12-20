# -*- coding: utf-8 -*-
import os
import time
import re
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
        self.setMinimumSize(550, 680)
        
        # State Data
        self.all_found_ids = []  # Stores ALL valid IDs found by the search
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
        
        # Option C: Date Range (NEW)
        hbox_range = QHBoxLayout()
        self.radio_range = QRadioButton("Between:")
        
        # Start Date
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("MM/dd HH:mm")
        
        # End Date
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
        
        # 2. Checkboxes Grid
        checks_layout = QGridLayout()
        self.chk_learning = QCheckBox("Learning")
        self.chk_learning.setChecked(True)
        self.chk_young = QCheckBox("Young")
        self.chk_young.setChecked(True)
        self.chk_mature = QCheckBox("Mature")
        self.chk_mature.setChecked(True)
        self.chk_horizontal = QCheckBox("Tree Search (Horizontal)")
        self.chk_horizontal.setToolTip("Finds ALL cards sharing IDs with your reviewed cards.")
        self.chk_include_correct = QCheckBox("Include Correct Questions")
        self.chk_include_correct.setToolTip("Include questions you already mastered in UWorld Helper.")
        
        checks_layout.addWidget(self.chk_learning, 0, 0)
        checks_layout.addWidget(self.chk_young, 0, 1)
        checks_layout.addWidget(self.chk_mature, 0, 2)
        checks_layout.addWidget(self.chk_horizontal, 1, 0, 1, 2)
        checks_layout.addWidget(self.chk_include_correct, 1, 2, 1, 2)
        settings_layout.addLayout(checks_layout)
        
        # 3. Batch Size
        batch_hbox = QHBoxLayout()
        batch_hbox.addWidget(QLabel("Output Limit (Batch Size):"))
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 1000)
        self.spin_limit.setValue(40) # Default to 40
        batch_hbox.addWidget(self.spin_limit)
        batch_hbox.addStretch()
        settings_layout.addLayout(batch_hbox)
        
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

    # ================= LOGIC =================

    def run_search(self):
        # 1. Get Time Parameters
        if self.radio_today.isChecked():
            start_ms = (mw.col.sched.day_cutoff - 86400) * 1000
            end_ms = time.time() * 1000 # Now
        elif self.radio_hours.isChecked():
            start_ms = (time.time() - (self.spin_hours.value() * 3600)) * 1000
            end_ms = time.time() * 1000
        else:
            # Range Selection (Convert QDateTime to MS Timestamp)
            start_ms = self.dt_start.dateTime().toMSecsSinceEpoch()
            end_ms = self.dt_end.dateTime().toMSecsSinceEpoch()

        states = {
            "learning": self.chk_learning.isChecked(),
            "young": self.chk_young.isChecked(),
            "mature": self.chk_mature.isChecked()
        }
        
        horizontal_mode = self.chk_horizontal.isChecked()
        include_correct = self.chk_include_correct.isChecked()

        # 2. Find IDs (Pass tuple of start/end)
        final_ids = self.find_ids_logic((start_ms, end_ms), states, horizontal_mode)
        
        # 3. Initial Filtering (Correct & Invalid)
        stats = {'found': len(final_ids), 'removed_correct': 0, 'removed_invalid': 0}
        
        # A. Filter Correct
        if not include_correct:
            correct_ids = load_correct_ids_from_helper()
            start_len = len(final_ids)
            final_ids = final_ids - correct_ids
            stats['removed_correct'] = start_len - len(final_ids)
            
        # B. Filter Invalid (Blocklist)
        invalid_ids = load_invalid_ids()
        start_len = len(final_ids)
        final_ids = final_ids - invalid_ids
        stats['removed_invalid'] = start_len - len(final_ids)
        
        # 4. Store & Display
        self.all_found_ids = sorted(list(final_ids), key=lambda x: int(x))
        self.refresh_display(update_timestamp=True, stats=stats)


    def find_ids_logic(self, time_range, states, horizontal_mode):
        start_ms, end_ms = time_range
        
        # Identify Reviewed Cards in RANGE
        query = f"SELECT DISTINCT cid FROM revlog WHERE id >= {int(start_ms)} AND id <= {int(end_ms)}"
        card_ids = mw.col.db.list(query)
        if not card_ids: return set()

        # Filter by State
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
        
        if not seed_nids: return set()

        # Extract UWorld IDs
        seed_uworld_ids = set()
        tag_regex = re.compile(r"(?i)UWorld.*::Step.*::(\d+)$")

        for nid in seed_nids:
            try:
                note = mw.col.get_note(nid)
                for tag in note.tags:
                    match = tag_regex.search(tag)
                    if match: seed_uworld_ids.add(match.group(1))
            except: continue

        # Horizontal Expansion
        final_ids = seed_uworld_ids
        if horizontal_mode and seed_uworld_ids:
            expanded_nids = set()
            for qid in seed_uworld_ids:
                ids_notes = mw.col.find_notes(f"tag:*UWorld*Step*::{qid}")
                expanded_nids.update(ids_notes)
            
            expanded_uworld_ids = set()
            for nid in expanded_nids:
                try:
                    note = mw.col.get_note(nid)
                    for tag in note.tags:
                        match = tag_regex.search(tag)
                        if match: expanded_uworld_ids.add(match.group(1))
                except: continue
            final_ids = expanded_uworld_ids
            
        return final_ids

    def refresh_display(self, update_timestamp=False, stats=None):
        limit = self.spin_limit.value()
        
        # Slice the list to the requested batch size
        self.displayed_ids = self.all_found_ids[:limit]
        
        # Update Text Area
        if self.displayed_ids:
            self.text_area.setPlainText(", ".join(self.displayed_ids))
        else:
            self.text_area.setPlainText("No IDs found matching criteria.")

        # Update Status Label
        if update_timestamp:
            t_str = datetime.now().strftime("%I:%M %p")
            count = len(self.all_found_ids)
            msg = f"Generated at {t_str}. Found {count} total valid IDs."
            
            if stats:
                details = []
                if stats['removed_correct']: details.append(f"{stats['removed_correct']} correct hidden")
                if stats['removed_invalid']: details.append(f"{stats['removed_invalid']} invalid hidden")
                if details: msg += f" ({', '.join(details)})"
                
            if count > limit:
                msg += f" <b>Showing first {limit}.</b>"
                
            self.lbl_status.setText(msg)
        else:
            # Simple refresh (e.g. after removing bad IDs)
            count = len(self.all_found_ids)
            self.lbl_status.setText(f"List updated. {count} valid IDs remaining. Showing first {limit}.")

    def open_filter_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, "Paste Error List", 
            "Paste the full error message from UWorld here:")
        if ok and text:
            self.remove_ids(text)

    def remove_ids(self, error_text):
        bad_ids = set(re.findall(r'\d+', error_text))
        if not bad_ids:
            tooltip("No numbers found in the pasted text.")
            return

        # 1. Save to permanent blocklist
        save_invalid_ids(bad_ids)
        
        # 2. Remove from CURRENT session memory
        original_count = len(self.all_found_ids)
        self.all_found_ids = [x for x in self.all_found_ids if x not in bad_ids]
        removed_count = original_count - len(self.all_found_ids)
        
        # 3. Refresh display (Auto-refill the batch)
        if removed_count > 0:
            self.refresh_display()
            tooltip(f"Removed {removed_count} IDs and refilled the list.")
        else:
            tooltip("Those IDs were not in the current list, but they have been saved to the blocklist.")

    def copy_to_clipboard(self):
        mw.app.clipboard().setText(self.text_area.toPlainText())
        tooltip("Copied!")

# ============================================================
# 3) ENTRY POINT
# ============================================================
def run_uworld_fetcher():
    global history_window
    
    # Create window if it doesn't exist
    if not history_window:
        history_window = UWorldHistoryFetcher(mw)
    
    # Show and bring to front (Modeless - allows interaction with other windows)
    history_window.show()
    history_window.raise_()
    history_window.activateWindow()

# Add to Tools Menu
action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)