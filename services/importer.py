import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List
from models.table import Table

logger = logging.getLogger("import_preview")


def get_excel_sheet_names(file_path: str) -> List[str]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".xls"):
        raise ValueError(f"Not an Excel file: {suffix}")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        with pd.ExcelFile(file_path, engine="openpyxl" if suffix == ".xlsx" else None) as xl:
            return xl.sheet_names
    except Exception as exc:
        raise ValueError(f"Cannot read Excel sheets: {exc}")


def load_file(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, engine="openpyxl" if suffix == ".xlsx" else None)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    logger.info(f"Loaded file {file_path}: {len(df)} rows, {len(df.columns)} columns")
    return df


def load_file_sheet(file_path: str, sheet_name: str = None) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".xls"):
        return load_file(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    engine = "openpyxl" if suffix == ".xlsx" else None
    if sheet_name is None:
        df = pd.read_excel(file_path, engine=engine)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine)
    logger.info(f"Loaded sheet '{sheet_name or 'first'}' from {file_path}: {len(df)} rows, {len(df.columns)} columns")
    return df


def get_preview(df: pd.DataFrame, max_rows: int = 30) -> pd.DataFrame:
    return df.head(max_rows)


def normalize_table(
    source_df: pd.DataFrame,
    column_mapping: Dict[str, int],
    starting_row: int,
    source_file: str,
    source_type: str,
    source_identifier: str,
) -> Table:
    if source_df is None or source_df.empty:
        raise ValueError("Source dataframe is empty")

    required_fields = [
        "Ret. Time",
        "CAS#",
        "S/N",
        "Base Peak m/z",
        "Area",
        "Area%",
        "Name",
    ]

    for field in required_fields:
        if field not in column_mapping:
            raise ValueError(f"Missing required field mapping: {field}")

    col_indices = list(column_mapping.values())
    if len(set(col_indices)) != len(col_indices):
        raise ValueError("Duplicate column mappings detected")

    data_start = starting_row - 1
    if data_start < 0 or data_start >= len(source_df):
        raise ValueError(
            f"Starting row {starting_row} is out of bounds for file with {len(source_df)} rows"
        )

    data = source_df.iloc[data_start:].reset_index(drop=True)

    selected_cols = {}
    for field, col_idx in column_mapping.items():
        zero_idx = col_idx - 1
        if 0 <= zero_idx < len(source_df.columns):
            selected_cols[field] = source_df.iloc[data_start:, zero_idx].reset_index(drop=True)
        else:
            selected_cols[field] = pd.Series([""] * len(data))

    normalized = pd.DataFrame(selected_cols)

    for field in ["Ret. Time", "S/N", "Base Peak m/z", "Area", "Area%"]:
        if field in normalized.columns:
            normalized[field] = pd.to_numeric(normalized[field], errors="coerce")
            if field == "Ret. Time":
                normalized[field] = normalized[field].round(3)

    normalized.columns = [str(c) for c in normalized.columns]

    table = Table(
        source_file=source_file,
        source_type=source_type,
        source_identifier=source_identifier,
        starting_row=starting_row,
        column_mapping=column_mapping,
        dataframe=normalized,
    )

    logger.info(
        f"Normalized {source_file} ({source_identifier}): {len(normalized)} peaks"
    )
    return table
