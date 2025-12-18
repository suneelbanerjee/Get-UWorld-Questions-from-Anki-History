from aqt import mw
from aqt.qt import *
from aqt.utils import showText, tooltip
import time
import re

# --- Class 1: The Result Window (Handles output and filtering) ---
class UWorldResultDialog(QDialog):
    def __init__(self, ids, batch_size, parent=None):
        super().__init__(parent)
        self.ids = ids 
        self.batch_size = batch_size
        self.setWindowTitle("UWorld IDs Found")
        self.setMinimumSize(600, 500)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        
        lbl = QLabel("<b>Step 1:</b> Copy these IDs into UWorld.<br>"
                     "<b>Step 2:</b> If UWorld errors on inactive questions, copy the error message.<br>"
                     "<b>Step 3:</b> Click 'Remove Bad IDs' below and paste the error.")
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

        original_count = len(self.ids)
        self.ids = [x for x in self.ids if x not in bad_ids]
        removed_count = original_count - len(self.ids)
        
        if removed_count > 0:
            self.update_display()
            tooltip(f"Removed {removed_count} invalid IDs.")
        else:
            tooltip("No matching IDs found to remove.")


# --- Class 2: The Setup Dialog ---
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
        self.chk_horizontal.setToolTip(
            "If Checked: Finds ALL cards that share a UWorld ID with your reviewed cards,\n"
            "then grabs ALL UWorld IDs from those cards too."
        )
        self.chk_horizontal.setChecked(False) 
        
        search_layout.addWidget(self.chk_horizontal)
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
        
        return cutoff_ms, states, self.spin_batch.value(), self.chk_horizontal.isChecked()

def run_uworld_fetcher():
    dialog = UWorldReverseFetcher(mw)
    if dialog.exec_():
        cutoff_ms, states, batch_size, horizontal_mode = dialog.get_query_parameters()
        find_and_extract_ids(cutoff_ms, states, batch_size, horizontal_mode)

def find_and_extract_ids(cutoff_ms, states, batch_size, horizontal_mode):
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
        except:
            continue

    if not seed_nids:
        tooltip("Cards found, but none matched the State criteria.")
        return

    # 3. Extract Seed IDs
    seed_uworld_ids = set()
    # UPDATED REGEX: Requires "UWorld" AND "Step" in the tag name
    # e.g. matches #AK...::#UWorld::Step::1234
    # e.g. ignores #AK...::#UWorld::Shelf::1234
    tag_regex = re.compile(r"(?i)UWorld.*::Step.*::(\d+)$")

    for nid in seed_nids:
        try:
            note = mw.col.get_note(nid)
            for tag in note.tags:
                match = tag_regex.search(tag)
                if match:
                    seed_uworld_ids.add(match.group(1))
        except:
            continue
            
    if not seed_uworld_ids:
        tooltip("Reviewed cards found, but they had no valid UWorld::Step tags.")
        return

    final_ids = seed_uworld_ids

    # 4. Horizontal Expansion (Tree Search)
    if horizontal_mode:
        expanded_nids = set()
        
        # We need to find notes that share the SAME exact Step IDs we just found
        for qid in seed_uworld_ids:
            # We use a wildcard search for tags containing that ID
            # But we must ensure the search query targets the Step tag specifically
            # This search finds notes having tag: ...UWorld...Step...[QID]
            ids_notes = mw.col.find_notes(f"tag:*UWorld*Step*::{qid}")
            expanded_nids.update(ids_notes)
            
        expanded_uworld_ids = set()
        for nid in expanded_nids:
            try:
                note = mw.col.get_note(nid)
                for tag in note.tags:
                    # Apply the same strict regex to the expanded cards
                    match = tag_regex.search(tag)
                    if match:
                        expanded_uworld_ids.add(match.group(1))
            except:
                continue
        
        final_ids = expanded_uworld_ids

    # 5. Output
    if final_ids:
        dialog = UWorldResultDialog(list(final_ids), batch_size, mw)
        dialog.exec_()
    else:
        tooltip("No UWorld Step IDs found.")

# Add to Tools Menu
action = QAction("Get UWorld IDs from History", mw)
action.triggered.connect(run_uworld_fetcher)
mw.form.menuTools.addAction(action)