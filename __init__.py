from aqt import mw
from aqt.qt import *
from aqt.utils import showText, tooltip
import time
import re

# --- Class 1: The Result Window (Handles output and filtering) ---
class UWorldResultDialog(QDialog):
    def __init__(self, ids, batch_size, parent=None):
        super().__init__(parent)
        self.ids = ids # List of ID strings
        self.batch_size = batch_size
        self.setWindowTitle("UWorld IDs Found")
        self.setMinimumSize(600, 500)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        
        # Instructions
        lbl = QLabel("<b>Step 1:</b> Copy these IDs into UWorld.<br>"
                     "<b>Step 2:</b> If UWorld gives an error about inactive questions, copy the error message.<br>"
                     "<b>Step 3:</b> Click 'Remove Bad IDs' below and paste the error to clean this list.")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # Text Area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(False)
        layout.addWidget(self.text_area)
        
        # Render initial text
        self.update_display()

        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_filter = QPushButton("Remove Bad IDs from UWorld Error...")
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

        # Sort numerically
        sorted_list = sorted(self.ids, key=lambda x: int(x))
        total_ids = len(sorted_list)
        
        display_text = []
        
        # Chunk list into batches
        for i in range(0, total_ids, self.batch_size):
            chunk = sorted_list[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            
            header = f"--- Batch {batch_num} ({len(chunk)} IDs) ---"
            ids_string = ", ".join(chunk)
            
            display_text.append(header)
            display_text.append(ids_string)
            display_text.append("") # Empty line for spacing

        self.text_area.setText("\n".join(display_text))

    def open_filter_dialog(self):
        # Ask user for the error text
        text, ok = QInputDialog.getMultiLineText(self, "Paste Error List", 
            "Paste the full error message from UWorld here\n(e.g. 'Please remove the following questions... 2518, 4288'):")
        
        if ok and text:
            self.remove_ids(text)

    def remove_ids(self, error_text):
        # Regex to find all sequences of digits in the error text
        bad_ids = set(re.findall(r'\d+', error_text))
        
        if not bad_ids:
            tooltip("No numbers found in the pasted text.")
            return

        original_count = len(self.ids)
        
        # Filter out the bad IDs
        self.ids = [x for x in self.ids if x not in bad_ids]
        
        removed_count = original_count - len(self.ids)
        
        if removed_count > 0:
            self.update_display()
            tooltip(f"Successfully removed {removed_count} invalid IDs.")
        else:
            tooltip("None of the IDs in the error message were found in your current list.")


# --- Class 2: The Setup Dialog (Timeframe & State) ---
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

# --- Main Functions ---
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

    # --- Step 4: Show Interactive Dialog ---
    if uworld_ids:
        # Pass the raw list to the dialog; the dialog handles sorting/batching/filtering
        dialog = UWorldResultDialog(list(uworld_ids), batch_size, mw)
        dialog.exec_()
    else:
        tooltip("Cards found, but no UWorld tags were detected.")

# Add to Tools Menu
action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)