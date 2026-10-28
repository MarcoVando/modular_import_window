import pandas as pd
import io
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


@dataclass
class Table:
    source_file: str
    source_type: str
    source_identifier: str
    starting_row: int
    column_mapping: Dict[str, int]
    dataframe: pd.DataFrame
    notes: str = ""

    def __post_init__(self):
        if self.dataframe is not None and "Peak Number" not in self.dataframe.columns:
            self.dataframe.insert(0, "Peak Number", range(1, len(self.dataframe) + 1))

    def get_peak_count(self) -> int:
        return len(self.dataframe) if self.dataframe is not None else 0

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "source_file": self.source_file,
            "source_type": self.source_type,
            "source_identifier": self.source_identifier,
            "starting_row": self.starting_row,
            "column_mapping": self.column_mapping,
            "notes": self.notes,
        }
        if self.dataframe is not None:
            d["dataframe"] = self.dataframe.to_json(orient="split", date_format="iso")
        else:
            d["dataframe"] = None
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Table":
        df = None
        if d.get("dataframe"):
            df = pd.read_json(io.StringIO(d["dataframe"]), orient="split")
        return cls(
            source_file=d["source_file"],
            source_type=d["source_type"],
            source_identifier=d["source_identifier"],
            starting_row=d["starting_row"],
            column_mapping=d["column_mapping"],
            dataframe=df,
            notes=d.get("notes", ""),
        )
