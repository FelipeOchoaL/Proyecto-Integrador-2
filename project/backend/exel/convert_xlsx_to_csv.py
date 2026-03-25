import csv
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE = SCRIPT_DIR / "ppulse-export.xlsx"
OUTPUT_FILE = SCRIPT_DIR / "ppulse-export.csv"


def convert():
    df = pd.read_excel(INPUT_FILE, dtype=str, na_filter=False)

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )

    verify = pd.read_csv(OUTPUT_FILE, dtype=str, keep_default_na=False)
    assert df.shape == verify.shape, f"Row/col mismatch: xlsx {df.shape} vs csv {verify.shape}"
    assert list(df.columns) == list(verify.columns), "Column names changed"

    mismatches = (df.values != verify.values).sum()
    assert mismatches == 0, f"{mismatches} cell value(s) differ after round-trip"

    print(f"Converted {len(df)} rows x {len(df.columns)} cols")
    print(f"Output: {OUTPUT_FILE}")
    print("Round-trip verification passed.")


if __name__ == "__main__":
    convert()
