import uuid
import logging
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QSpinBox, QCheckBox, QLabel, QHeaderView, QSplitter,
    QMessageBox, QFileDialog, QGroupBox, QFormLayout, QApplication,
    QDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor, QBrush
from services.importer import load_file, get_preview, normalize_table, get_excel_sheet_names, load_file_sheet
from models.table import Table


logger = logging.getLogger("import_preview")

FIELD_COLORS = {
    "Ret. Time": QColor("#A6CEE3"),
    "CAS#": QColor("#B2DF8A"),
    "S/N": QColor("#FB9A99"),
    "Base Peak m/z": QColor("#CAB2D6"),
    "Area": QColor("#FF7F00"),
    "Area%": QColor("#FFFF99"),
    "Name": QColor("#FDBF6F"),
}


def sheet_display_name(file_path: str, sheet_name: str) -> str:
    """Label for one sheet of a workbook: the path with the sheet name.

    The sheet name is what identifies the entity once a workbook is split into
    its sheets, so it is shown instead of a "sheet 2 of 3" counter.
    """
    if not sheet_name:
        return file_path
    return f"{file_path} ({sheet_name})"


class ImportWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, file_path, column_mapping, starting_row, source_identifier, source_type):
        super().__init__()
        self.file_path = file_path
        self.column_mapping = column_mapping
        self.starting_row = starting_row
        self.source_identifier = source_identifier
        self.source_type = source_type

    def run(self):
        try:
            df = load_file(self.file_path)
            preview = get_preview(df)
            table = normalize_table(
                df,
                self.column_mapping,
                self.starting_row,
                self.file_path,
                self.source_type,
                self.source_identifier,
            )
            self.finished.emit({"preview": preview, "table": table, "file_path": self.file_path})
        except Exception as e:
            logger.exception(f"Import error for {self.file_path}")
            self.error.emit(str(e))


class FileConfigWidget(QWidget):
    configChanged = Signal(dict)
    removeRequested = Signal()

    def __init__(self, file_path, parent=None, sheet_name=None, display_name=None, config_id=None):
        super().__init__(parent)
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.display_name = display_name or file_path
        self.config_id = config_id or str(uuid.uuid4())
        self.df = None
        self.column_mapping = {}
        self.starting_row = 1
        self.source_identifier = ""
        self.source_type = "NORMAL"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)
        self.file_label = QLabel(display_name or file_path)
        self.file_label.setWordWrap(True)
        header_layout.addWidget(self.file_label)
        layout.addLayout(header_layout)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(0)
        self.preview_table.setRowCount(0)
        self.preview_table.setAlternatingRowColors(False)
        layout.addWidget(self.preview_table, 1)

        mapping_group = QGroupBox("Column Mapping")
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(2)
        form_layout.setContentsMargins(4, 4, 4, 4)
        self.spinboxes = {}
        for field in [
            "Var 1",
            "Var 2",
            "Var 3",
            "Var 4",
            "Var 5",
            "Var 6",
            "Var 7",
        ]:
            spin = QSpinBox()
            spin.setMinimum(0)
            spin.setMaximum(100)
            spin.setValue(0)
            spin.setSpecialValueText("Not set")
            spin.valueChanged.connect(self._on_mapping_changed)
            self.spinboxes[field] = spin
            form_layout.addRow(field, spin)
        # Auto-fill button
        autofill_layout = QHBoxLayout()
        autofill_btn = QPushButton("Auto-fill from Header")
        autofill_btn.setToolTip("Attempt to match column headers to field names")
        autofill_btn.clicked.connect(self._auto_fill_from_header)
        autofill_layout.addWidget(autofill_btn)

        default_btn = QPushButton("Set Default (1-7)")
        default_btn.setToolTip("Set columns 1 through 7 for the 7 required fields")
        default_btn.clicked.connect(self._set_default_mapping)
        autofill_layout.addWidget(default_btn)

        autofill_layout.addStretch()
        form_layout.addRow(autofill_layout)

        mapping_group.setLayout(form_layout)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        bottom_layout.addWidget(mapping_group, 1)

        col2_layout = QVBoxLayout()
        col2_layout.setSpacing(6)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(4)
        row_layout.addWidget(QLabel("Data starts at row (1-based):"))
        self.row_spinbox = QSpinBox()
        self.row_spinbox.setMinimum(1)
        self.row_spinbox.setMaximum(10000)
        self.row_spinbox.setValue(1)
        self.row_spinbox.setStyleSheet("""
            QSpinBox {
                border: 2px solid #2C3E50;
                border-radius: 3px;
                padding: 4px;
                background-color: white;
                min-width: 80px;
            }
            QSpinBox:focus {
                border-color: #2E86DE;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 16px;
                border: none;
                background: #ECF0F1;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #BDC3C7;
            }
        """)
        self.row_spinbox.valueChanged.connect(self._on_row_changed)
        row_layout.addWidget(self.row_spinbox)
        col2_layout.addLayout(row_layout)

        self.status_label = QLabel("No file loaded")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        col2_layout.addWidget(self.status_label)

        self.side_container = QWidget()
        self.side_layout = QVBoxLayout(self.side_container)
        self.side_layout.setContentsMargins(0, 0, 0, 0)
        self.side_layout.setSpacing(4)
        self.side_layout.addStretch(1)
        col2_layout.addWidget(self.side_container, 1)

        bottom_layout.addLayout(col2_layout, 1)

        col3_layout = QVBoxLayout()
        col3_layout.setSpacing(6)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.removeRequested.emit)
        col3_layout.addWidget(remove_btn)
        col3_layout.addStretch(1)

        bottom_layout.addLayout(col3_layout, 1)
        layout.addLayout(bottom_layout)

    def set_side_widget(self, widget):
        if widget is None:
            return
        widget.setParent(self.side_container)
        self.side_layout.removeWidget(widget)
        self.side_layout.insertWidget(0, widget)

    def clear_side_widget(self, widget):
        if widget is not None and widget.parentWidget() is self.side_container:
            self.side_layout.removeWidget(widget)
            widget.setParent(None)

    def load_file(self):
        try:
            if self.sheet_name:
                self.df = load_file_sheet(self.file_path, self.sheet_name)
            else:
                self.df = load_file(self.file_path)
            self.status_label.setText(
                f"Loaded: {len(self.df)} rows, {len(self.df.columns)} columns"
            )
            self._update_preview()
            self._emit_config()
        except Exception as e:
            logger.exception(f"Failed to load file {self.file_path}")
            QMessageBox.critical(self, "Import Error", str(e))

    def _update_preview(self):
        if self.df is None:
            return
        start = max(0, self.row_spinbox.value() - 6)
        preview = self.df.iloc[start:start + 30]
        self.preview_table.setAlternatingRowColors(False)
        self.preview_table.setColumnCount(len(preview.columns))
        self.preview_table.setRowCount(len(preview))
        self.preview_table.setHorizontalHeaderLabels([str(c) for c in preview.columns])
        self.preview_table.horizontalHeader().setStretchLastSection(True)

        for i, row in preview.iterrows():
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val) if not pd.isna(val) else "")
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                item.setBackground(QColor("white"))
                self.preview_table.setItem(i, j, item)

        self._highlight_columns()
        self._highlight_starting_row()

    def _highlight_columns(self):
        if self.df is None:
            return
        self.preview_table.setUpdatesEnabled(False)
        for row in range(self.preview_table.rowCount()):
            for col in range(self.preview_table.columnCount()):
                item = self.preview_table.item(row, col)
                if item:
                    item.setBackground(QColor("white"))
        for field, spin in self.spinboxes.items():
            col_idx = spin.value() - 1
            color = FIELD_COLORS.get(field, QColor("white"))
            if 0 <= col_idx < self.preview_table.columnCount():
                for row in range(self.preview_table.rowCount()):
                    item = self.preview_table.item(row, col_idx)
                    if item:
                        item.setBackground(color)
        self.preview_table.setUpdatesEnabled(True)

    def _highlight_starting_row(self):
        if self.df is None:
            return
        self._highlight_columns()
        start = max(0, self.row_spinbox.value() - 6)
        for r in range(self.preview_table.rowCount()):
            actual = start + r + 1
            if actual < self.row_spinbox.value():
                for col in range(self.preview_table.columnCount()):
                    item = self.preview_table.item(r, col)
                    if item:
                        item.setBackground(QColor("#D9D9D9"))
        row = self.row_spinbox.value() - 1 - start
        if 0 <= row < self.preview_table.rowCount():
            for col in range(self.preview_table.columnCount()):
                item = self.preview_table.item(row, col)
                if item:
                    item.setBackground(QColor("#FFF2CC"))

    def _on_mapping_changed(self):
        if self.df is None:
            return
        mapping = {f: s.value() for f, s in self.spinboxes.items() if s.value() > 0}
        col_vals = list(mapping.values())
        if len(col_vals) != len(set(col_vals)):
            self.status_label.setText("Warning: duplicate column mapping")
        else:
            self.status_label.setText(f"Mapped {len(mapping)} fields")
        self._highlight_columns()
        self._highlight_starting_row()
        self._emit_config()

    def _on_row_changed(self):
        self.starting_row = self.row_spinbox.value()
        self._highlight_starting_row()
        self._emit_config()


    def _auto_fill_from_header(self):
        if self.df is None:
            return
        # Normalize header names for matching
        headers = [str(c).strip().lower() for c in self.df.columns]
        header_to_idx = {h: i + 1 for i, h in enumerate(headers)}

        # Field name variations for matching
        field_variations = {
            "Ret. Time": ["ret. time", "ret time", "retention time", "rt", "retention_time"],
            "CAS#": ["cas#", "cas", "cas no", "cas number", "cas_number"],
            "S/N": ["s/n", "sn", "signal/noise", "signal to noise", "s_n"],
            "Base Peak m/z": ["base peak m/z", "base peak mz", "base peak", "m/z", "mz", "base_peak_mz"],
            "Area": ["area", "peak area", "peak_area"],
            "Area%": ["area%", "area %", "area percent", "area_percent", "percent area"],
            "Name": ["name", "compound name", "compound", "compound_name"],
        }

        for field, variations in field_variations.items():
            spin = self.spinboxes[field]
            if spin.value() > 0:
                continue  # Already set
            for var in variations:
                if var in header_to_idx:
                    spin.setValue(header_to_idx[var])
                    break

        self._on_mapping_changed()

    def _set_default_mapping(self):
        # Set columns 1-7 for the 7 required fields in order
        fields = [
            "Var 1",
            "Var 2",
            "Var 3",
            "Var 4",
            "Var 5",
            "Var 6",
            "Var 7",
        ]
        for i, field in enumerate(fields):
            self.spinboxes[field].setValue(i + 1)
        self._on_mapping_changed()

    def get_config(self):
        mapping = {f: s.value() for f, s in self.spinboxes.items()}
        return {
            "config_id": self.config_id,
            "file_path": self.file_path,
            "sheet_name": self.sheet_name,
            "display_name": self.display_name,
            "column_mapping": mapping,
            "starting_row": self.row_spinbox.value(),
            "source_identifier": self.source_identifier,
            "source_type": self.source_type,
        }

    def _emit_config(self):
        self.configChanged.emit(self.get_config())

    def set_source_identifier(self, identifier):
        self.source_identifier = identifier
        self._emit_config()


class ImportWindow(QMainWindow):
    filesImported = Signal(list)

    def __init__(self, parent=None, existing_peak_tables=None):
        super().__init__(parent)
        self.setWindowTitle("Import Files")
        self.resize(900, 600)
        self.file_configs = []

        # Compute next identifiers based on existing tables
        normal_count = sum(1 for pt in (existing_peak_tables or []) if pt.source_type == "NORMAL")
        self.next_normal = normal_count + 1

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        add_btn = QPushButton("Add Files")
        add_btn.clicked.connect(self._add_files)
        import_btn = QPushButton("Import All")
        import_btn.clicked.connect(self._import_all)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.file_list.setFixedWidth(240)
        self.stack.currentChanged.connect(self._relocate_file_list)

    def _relocate_file_list(self):
        widget = self.stack.currentWidget()
        if isinstance(widget, FileConfigWidget):
            widget.set_side_widget(self.file_list)
        else:
            self.file_list.setParent(None)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "", "Excel/CSV Files (*.xlsx *.xls *.csv)"
        )
        for f in files:
            if f in [c["file_path"] for c in self.file_configs]:
                continue

            # Check for multiple Excel sheets
            sheet_names = None
            if f.lower().endswith((".xlsx", ".xls")):
                try:
                    sheet_names = get_excel_sheet_names(f)
                except Exception as exc:
                    logger.warning(f"Cannot read Excel sheets for {f}: {exc}")

            if sheet_names and len(sheet_names) > 1:
                # Ask user if they want to extract each sheet as a separate file
                reply = QMessageBox.question(
                    self,
                    "Multiple Sheets Detected",
                    f"File '{f}' contains {len(sheet_names)} sheets.\n\n"
                    "Extract each sheet as a separate file?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    for sheet in sheet_names:
                        display_name = sheet_display_name(f, sheet)
                        config_id = str(uuid.uuid4())
                        config = {
                            "config_id": config_id,
                            "file_path": f,
                            "sheet_name": sheet,
                            "display_name": display_name,
                            "column_mapping": {k: 0 for k in ["Var 1", "Var 2", "Var 3", "Var 4", "Var 5", "Var 6", "Var 7"]},
                            "starting_row": 1,
                                            "source_identifier": "",
                            "source_type": "NORMAL",
                        }
                        self.file_configs.append(config)
                        self.file_list.addItem(display_name)
                        idx = len(self.file_configs) - 1
                        widget = FileConfigWidget(f, sheet_name=sheet, display_name=display_name, config_id=config_id)
                        widget.configChanged.connect(self._on_config_changed)
                        widget.removeRequested.connect(self._remove_file)
                        widget.load_file()
                        self.stack.addWidget(widget)
                        self.file_list.setCurrentRow(idx)
                        widget.set_side_widget(self.file_list)
                else:
                    # Use first sheet only
                    display_name = sheet_display_name(f, sheet_names[0])
                    config_id = str(uuid.uuid4())
                    config = {
                        "config_id": config_id,
                        "file_path": f,
                        "sheet_name": sheet_names[0],
                        "display_name": display_name,
                        "column_mapping": {k: 0 for k in ["Var 1", "Var 2", "Var 3", "Var 4", "Var 5", "Var 6", "Var 7"]},
                        "starting_row": 1,
                                    "source_identifier": "",
                        "source_type": "NORMAL",
                    }
                    self.file_configs.append(config)
                    self.file_list.addItem(display_name)
                    idx = len(self.file_configs) - 1
                    widget = FileConfigWidget(f, sheet_name=sheet_names[0], display_name=display_name, config_id=config_id)
                    widget.configChanged.connect(self._on_config_changed)
                    widget.removeRequested.connect(self._remove_file)
                    widget.load_file()
                    self.stack.addWidget(widget)
                    self.file_list.setCurrentRow(idx)
                    widget.set_side_widget(self.file_list)
            else:
                # CSV, a single-sheet workbook, or a workbook whose sheets
                # could not be read: the first sheet is the whole file.
                display_name = f
                config_id = str(uuid.uuid4())
                config = {
                    "config_id": config_id,
                    "file_path": f,
                    "sheet_name": None,
                    "display_name": display_name,
                    "column_mapping": {k: 0 for k in ["Var 1", "Var 2", "Var 3", "Var 4", "Var 5", "Var 6", "Var 7"]},
                    "starting_row": 1,
                            "source_identifier": "",
                    "source_type": "NORMAL",
                }
                self.file_configs.append(config)
                self.file_list.addItem(f)
                idx = len(self.file_configs) - 1
                widget = FileConfigWidget(f, config_id=config_id)
                widget.configChanged.connect(self._on_config_changed)
                widget.removeRequested.connect(self._remove_file)
                widget.load_file()
                self.stack.addWidget(widget)
                self.file_list.setCurrentRow(idx)
                widget.set_side_widget(self.file_list)

    def _assign_identifiers(self):
        idx = self.next_normal
        for c in self.file_configs:
            if idx <= 26:
                c["source_identifier"] = chr(64 + idx)
            else:
                c["source_identifier"] = chr(64 + idx // 26) + chr(64 + idx % 26)
            c["source_type"] = "NORMAL"
            idx += 1

    def _on_config_changed(self, config):
        for i, c in enumerate(self.file_configs):
            if c.get("config_id") == config.get("config_id"):
                c["column_mapping"] = config["column_mapping"]
                c["starting_row"] = config["starting_row"]
                c["source_type"] = config["source_type"]
                break

    def _remove_file(self):
        current_widget = self.stack.currentWidget()
        if current_widget is None:
            return
        config_id = current_widget.config_id
        self.file_configs = [c for c in self.file_configs if c.get("config_id") != config_id]
        self.file_list.takeItem(self.file_list.currentRow())
        current_widget.clear_side_widget(self.file_list)
        self.stack.removeWidget(current_widget)
        current_widget.deleteLater()
        self._assign_identifiers()

    def _import_all(self):
        if not self.file_configs:
            QMessageBox.warning(self, "Warning", "No files configured")
            return
        # Assign identifiers now so the letters reflect the final set after
        # any deletions and BCO toggles made in this window.
        self._assign_identifiers()
        for c in self.file_configs:
            mapping = c.get("column_mapping", {})
            mapped = {k: v for k, v in mapping.items() if v > 0}
            if len(mapped) < 7:
                missing = [f for f in ["Var 1", "Var 2", "Var 3", "Var 4", "Var 5", "Var 6", "Var 7"] if f not in mapped]
                QMessageBox.warning(
                    self, "Warning",
                    f"File {c['file_path']} does not have all required fields mapped.\n"
                    f"Missing: {', '.join(missing)}"
                )
                return
        self.filesImported.emit(self.file_configs)
        self.close()
