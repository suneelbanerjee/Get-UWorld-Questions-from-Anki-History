from aqt import mw
from aqt.qt import *
from aqt.utils import showText, tooltip
import time
import re

class UWorldReverseFetcher(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Get UWorld IDs from Reviewed Cards")
        self.setMinimumWidth(450)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # --- Section 1: Timeframe ---
        time_group = QGroupBox("1. Timeframe (When did you review them?)")
        time_layout = QVBoxLayout()
        
        self.radio_today = QRadioButton("Reviewed Today (since start of current day)")
        self.radio_today.setChecked(True)
        
        self.radio_hours = QRadioButton("Reviewed in the last:")
        
        self.spin_hours = QSpinBox()
        self.spin_hours.setRange(1, 1000)
        self.spin_hours.setValue(4) # Default to last 4 hours
        self.spin_hours.setSuffix(" hours")
        
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.radio_hours)
        h_layout.addWidget(self.spin_hours)
        h_layout.addStretch()

        time_layout.addWidget(self.radio_today)
        time_layout.addLayout(h_layout)
        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # --- Section 2: Card State ---
        state_group = QGroupBox("2. Current Card State (Only include cards that are...)")
        state_layout = QVBoxLayout()
        
        # Queue 1/3
        self.chk_learning = QCheckBox("Learning / Relearning")
        self.chk_learning.setChecked(True)
        
        # Queue 2 + Interval < 21
        self.chk_young = QCheckBox("Young (Review interval < 21 days)")
        self.chk_young.setChecked(True)
        
        # Queue 2 + Interval >= 21
        self.chk_mature = QCheckBox("Mature (Review interval >= 21 days)")
        self.chk_mature.setChecked(True)

        state_layout.addWidget(self.chk_learning)
        state_layout.addWidget(self.chk_young)
        state_layout.addWidget(self.chk_mature)
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        # --- Section 3: Output Settings ---
        output_group = QGroupBox("3. Output Settings")
        output_layout = QHBoxLayout()
        
        output_layout.addWidget(QLabel("Max IDs per copy-paste block:"))
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 1000)
        self.spin_batch.setValue(40) # Default to 40 (UWorld max)
        self.spin_batch.setToolTip("UWorld typically allows max 40 questions per test.")
        
        output_layout.addWidget(self.spin_batch)
        output_layout.addStretch()
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # --- Buttons ---
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.setLayout(layout)

    def get_query_parameters(self):
        # 1. Calculate Time Cutoff (in milliseconds)
        if self.radio_today.isChecked():
            # mw.col.sched.day_cutoff is the timestamp for the START of the NEXT day.
            # We subtract 24 hours (86400 seconds) to get the start of the CURRENT day.
            cutoff_seconds = mw.col.sched.day_cutoff - 86400
            cutoff_ms = cutoff_seconds * 1000
        else:
            # Current time minus X hours
            hours = self.spin_hours.value()
            cutoff_ms = (time.time() - (hours * 3600)) * 1000

        # 2. Get State Booleans
        states = {
            "learning": self.chk_learning.isChecked(),
            "young": self.chk_young.isChecked(),
            "mature": self.chk_mature.isChecked()
        }
        
        # 3. Get Batch Size
        batch_size = self.spin_batch.value()
        
        return cutoff_ms, states, batch_size

def run_uworld_fetcher():
    dialog = UWorldReverseFetcher(mw)
    if dialog.exec_():
        cutoff_ms, states, batch_size = dialog.get_query_parameters()
        find_and_extract_ids(cutoff_ms, states, batch_size)

def find_and_extract_ids(cutoff_ms, states, batch_size):
    # --- Step 1: Find cards reviewed after cutoff ---
    query = f"SELECT DISTINCT cid FROM revlog WHERE id > {int(cutoff_ms)}"
    card_ids = mw.col.db.list(query)

    if not card_ids:
        tooltip("No cards reviewed in this timeframe.")
        return

    # --- Step 2: Filter by Current State ---
    valid_nids = set()
    
    for cid in card_ids:
        try:
            c = mw.col.get_card(cid)
        except:
            continue 
            
        is_learning = c.queue in (1, 3)
        is_review = c.queue == 2
        is_young = is_review and c.ivl < 21
        is_mature = is_review and c.ivl >= 21
        
        keep = False
        if is_learning and states['learning']:
            keep = True
        elif is_young and states['young']:
            keep = True
        elif is_mature and states['mature']:
            keep = True
            
        if keep:
            valid_nids.add(c.nid)

    if not valid_nids:
        tooltip("Cards found, but none matched the selected State criteria.")
        return

    # --- Step 3: Extract UWorld IDs from Tags ---
    uworld_ids = set()
    tag_regex = re.compile(r"(?i)UWorld.*::(\d+)$")

    for nid in valid_nids:
        try:
            note = mw.col.get_note(nid)
            for tag in note.tags:
                match = tag_regex.search(tag)
                if match:
                    uworld_ids.add(match.group(1))
        except:
            continue

    # --- Step 4: Output in Batches ---
    if uworld_ids:
        sorted_list = sorted(list(uworld_ids), key=lambda x: int(x))
        total_ids = len(sorted_list)
        
        display_text = []
        
        # Chunk list into batches
        for i in range(0, total_ids, batch_size):
            chunk = sorted_list[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            
            header = f"--- Batch {batch_num} ({len(chunk)} IDs) ---"
            ids_string = ", ".join(chunk)
            
            display_text.append(header)
            display_text.append(ids_string)
            display_text.append("") # Empty line for spacing

        final_string = "\n".join(display_text)
        showText(final_string, title=f"Found {total_ids} UWorld IDs")
    else:
        tooltip("Cards found, but no UWorld tags were detected.")

# Add to Tools Menu
action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)