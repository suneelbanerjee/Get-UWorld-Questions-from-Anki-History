# -*- coding: utf-8 -*-
import os
import time
import re
from aqt import mw
from aqt.qt import *
from aqt.utils import showText, tooltip

# ============================================================
# 1) FILE I/O HELPERS (Correct & Invalid Lists)
# ============================================================

def get_local_data_dir():
    """Returns the user_data folder for THIS add-on (History Fetcher)."""
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(addon_dir, "user_data")
    if not os.path.exists(data_dir):
        try: os.makedirs(data_dir)
        except: pass
    return data_dir

def load_correct_ids_from_helper():
    """
    Looks for correct_questions.txt in the sibling 'UWorld_Helper' add-on folder.
    """
    try:
        addons_dir = mw.addonManager.addonsFolder()
        target_path = os.path.join(addons_dir, "UWorld_Helper", "user_data", "correct_questions.txt")
        
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
                return set(x.strip() for x in content.split(",") if x.strip().isdigit())
    except Exception as e:
        print(f"Error loading correct IDs: {e}")
    return set()

def load_invalid_ids():
    """Loads locally saved invalid IDs (questions that error out)."""
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
    """Saves new invalid IDs to the local blocklist."""
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
# 2) Result Dialog (UI)
# ============================================================
class UWorldResultDialog(QDialog):
    def __init__(self, ids, batch_size, stats=None, parent=None):
        super().__init__(parent)
        self.ids = ids 
        self.batch_size = batch_size
        self.stats = stats if stats else {}
        self.setWindowTitle("UWorld IDs Found")
        self.setMinimumSize(600, 500)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        
        # Header text
        header = (
            "<b>Step 1:</b> Copy these IDs into UWorld.<br>"
            "<b>Step 2:</b> If UWorld errors, click 'Remove Bad IDs' and paste the error.<br>"
            "<i>(Bad IDs will be saved and blocked forever)</i>"
        )
        
        # Add Filter Stats
        filtered_msgs = []
        if self.stats.get('correct_removed'):
            filtered_msgs.append(f"{self.stats['correct_removed']} correct questions")
        if self.stats.get('invalid_removed'):
            filtered_msgs.append(f"{self.stats['invalid_removed']} invalid questions")
            
        if filtered_msgs:
            header += f"<br><br><i>Automatically removed: {', '.join(filtered_msgs)}.</i>"
            
        lbl = QLabel(header)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(False)
        layout.addWidget(self.text_area)
        
        self.update_display()

        btn_layout = QHBoxLayout()
        self.btn_filter = QPushButton("Remove Bad IDs from Error...")
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_filter)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def update_display(self):
        if not self.ids:
            self.text_area.setText("No IDs remaining.")
            return

        sorted_list = sorted(self.ids, key=lambda x: int(x))
        total_ids = len(sorted_list)
        
        display_text = []
        for i in range(0, total_ids, self.batch_size):
            chunk = sorted_list[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            header = f"--- Batch {batch_num} ({len(chunk)} IDs) ---"
            ids_string = ", ".join(chunk)
            display_text.append(header)
            display_text.append(ids_string)
            display_text.append("") 

        self.text_area.setText("\n".join(display_text))

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

        # 1. Save these bad IDs to disk immediately
        save_invalid_ids(bad_ids)

        # 2. Remove from current view
        original_count = len(self.ids)
        self.ids = [x for x in self.ids if x not in bad_ids]
        removed_count = original_count - len(self.ids)
        
        if removed_count > 0:
            self.update_display()
            tooltip(f"Removed {removed_count} invalid IDs and saved them to blocklist.")
        else:
            tooltip("IDs saved to blocklist (none were in current list).")

# ============================================================
# 3) Setup Dialog (Config)
# ============================================================
class UWorldReverseFetcher(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Get UWorld IDs from Reviewed Cards")
        self.setMinimumWidth(450)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # 1. Timeframe
        time_group = QGroupBox("1. Timeframe")
        time_layout = QVBoxLayout()
        self.radio_today = QRadioButton("Reviewed Today")
        self.radio_today.setChecked(True)
        self.radio_hours = QRadioButton("Reviewed in the last:")
        self.spin_hours = QSpinBox()
        self.spin_hours.setRange(1, 1000)
        self.spin_hours.setValue(4)
        self.spin_hours.setSuffix(" hours")
        
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.radio_hours)
        h_layout.addWidget(self.spin_hours)
        h_layout.addStretch()
        time_layout.addWidget(self.radio_today)
        time_layout.addLayout(h_layout)
        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # 2. State
        state_group = QGroupBox("2. Card State")
        state_layout = QVBoxLayout()
        self.chk_learning = QCheckBox("Learning / Relearning")
        self.chk_learning.setChecked(True)
        self.chk_young = QCheckBox("Young (< 21 days)")
        self.chk_young.setChecked(True)
        self.chk_mature = QCheckBox("Mature (>= 21 days)")
        self.chk_mature.setChecked(True)
        state_layout.addWidget(self.chk_learning)
        state_layout.addWidget(self.chk_young)
        state_layout.addWidget(self.chk_mature)
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        # 3. Search Mode
        search_group = QGroupBox("3. Search Logic")
        search_layout = QVBoxLayout()
        
        self.chk_horizontal = QCheckBox("Enable Horizontal Search (Tree Search)")
        self.chk_horizontal.setToolTip("Finds ALL cards sharing IDs with your reviewed cards.")
        self.chk_horizontal.setChecked(False) 
        search_layout.addWidget(self.chk_horizontal)

        self.chk_include_correct = QCheckBox("Include questions previously answered correctly")
        self.chk_include_correct.setToolTip("Check to re-do questions you already mastered.")
        self.chk_include_correct.setChecked(False) 
        search_layout.addWidget(self.chk_include_correct)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # 4. Output
        output_group = QGroupBox("4. Output Settings")
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Batch Size:"))
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 1000)
        self.spin_batch.setValue(40)
        output_layout.addWidget(self.spin_batch)
        output_layout.addStretch()
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self.setLayout(layout)

    def get_query_parameters(self):
        if self.radio_today.isChecked():
            cutoff_ms = (mw.col.sched.day_cutoff - 86400) * 1000
        else:
            cutoff_ms = (time.time() - (self.spin_hours.value() * 3600)) * 1000

        states = {
            "learning": self.chk_learning.isChecked(),
            "young": self.chk_young.isChecked(),
            "mature": self.chk_mature.isChecked()
        }
        
        return cutoff_ms, states, self.spin_batch.value(), self.chk_horizontal.isChecked(), self.chk_include_correct.isChecked()

# ============================================================
# 4) Main Logic
# ============================================================
def run_uworld_fetcher():
    dialog = UWorldReverseFetcher(mw)
    if dialog.exec_():
        cutoff_ms, states, batch_size, horizontal_mode, include_correct = dialog.get_query_parameters()
        find_and_extract_ids(cutoff_ms, states, batch_size, horizontal_mode, include_correct)

def find_and_extract_ids(cutoff_ms, states, batch_size, horizontal_mode, include_correct):
    # 1. Identify Reviewed Cards
    query = f"SELECT DISTINCT cid FROM revlog WHERE id > {int(cutoff_ms)}"
    card_ids = mw.col.db.list(query)

    if not card_ids:
        tooltip("No cards reviewed in this timeframe.")
        return

    # 2. Filter by State -> Get Seed NIDs
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
            
            if keep:
                seed_nids.add(c.nid)
        except: continue

    if not seed_nids:
        tooltip("Cards found, but none matched the State criteria.")
        return

    # 3. Extract Seed IDs
    seed_uworld_ids = set()
    tag_regex = re.compile(r"(?i)UWorld.*::Step.*::(\d+)$")

    for nid in seed_nids:
        try:
            note = mw.col.get_note(nid)
            for tag in note.tags:
                match = tag_regex.search(tag)
                if match:
                    seed_uworld_ids.add(match.group(1))
        except: continue
            
    if not seed_uworld_ids:
        tooltip("Reviewed cards found, but they had no valid UWorld::Step tags.")
        return

    final_ids = seed_uworld_ids

    # 4. Horizontal Expansion
    if horizontal_mode:
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
                    if match:
                        expanded_uworld_ids.add(match.group(1))
            except: continue
        final_ids = expanded_uworld_ids

    # 5. FILTERS (Correct & Invalid)
    original_count = len(final_ids)
    stats = {'correct_removed': 0, 'invalid_removed': 0}
    
    # A. Filter Correct (from Helper)
    if not include_correct:
        correct_ids = load_correct_ids_from_helper()
        before_correct = len(final_ids)
        final_ids = final_ids - correct_ids
        stats['correct_removed'] = before_correct - len(final_ids)

    # B. Filter Invalid (from Blocklist) - Always active
    invalid_ids = load_invalid_ids()
    before_invalid = len(final_ids)
    final_ids = final_ids - invalid_ids
    stats['invalid_removed'] = before_invalid - len(final_ids)

    # 6. Output
    if final_ids:
        dialog = UWorldResultDialog(list(final_ids), batch_size, stats, mw)
        dialog.exec_()
    else:
        # User feedback if everything was filtered
        msg = []
        if stats['correct_removed']: msg.append(f"{stats['correct_removed']} correct")
        if stats['invalid_removed']: msg.append(f"{stats['invalid_removed']} invalid")
        
        if msg:
            tooltip(f"All found questions were skipped! ({', '.join(msg)})")
        else:
            tooltip("No UWorld Step IDs found.")

# Add to Tools Menu
action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)