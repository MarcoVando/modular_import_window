import sys
import pandas as pd
from PySide6.QtWidgets import QApplication
from ui.import_window import ImportWindow
from services.importer import normalize_table, load_file, load_file_sheet


def main():
    app = QApplication(sys.argv)
    window = ImportWindow()

    def on_imported(configs):
        tables = []
        frames = []
        for c in configs:
            if c.get("sheet_name"):
                df = load_file_sheet(c["file_path"], c["sheet_name"])
            else:
                df = load_file(c["file_path"])
            table = normalize_table(
                df,
                c["column_mapping"],
                c["starting_row"],
                c["file_path"],
                c["source_type"],
                c["source_identifier"],
            )
            tables.append(table)
            frames.append(table.dataframe)
        merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        print("Per-file dataframes:", len(frames))
        print("Merged shape:", merged.shape)
        print(merged.head())
        window.close()

    window.filesImported.connect(on_imported)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
