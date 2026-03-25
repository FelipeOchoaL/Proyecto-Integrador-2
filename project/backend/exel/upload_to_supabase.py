import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
CSV_FILE = SCRIPT_DIR / "ppulse-export.csv"

load_dotenv(BACKEND_DIR / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

TABLE_NAME = "patentes"
BATCH_SIZE = 500

COLUMN_MAP = {
    "pn": "pn",
    "pc": "pc",
    "cpc": "cpc",
    "ic": "ic",
    "ws": "ws",
    "ls": "ls",
    "ti": "ti",
    "ab": "ab",
    "desc": "descripcion",
    "claimen*": "claimen",
    "espacenet": "espacenet",
}


def upload():
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    with open(CSV_FILE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        batch = []
        total = 0

        for row in reader:
            mapped = {COLUMN_MAP[k]: v for k, v in row.items() if k in COLUMN_MAP}
            batch.append(mapped)

            if len(batch) >= BATCH_SIZE:
                supabase.table(TABLE_NAME).insert(batch).execute()
                total += len(batch)
                print(f"  Insertadas {total} filas...")
                batch = []

        if batch:
            supabase.table(TABLE_NAME).insert(batch).execute()
            total += len(batch)

    print(f"Listo! Se insertaron {total} filas en la tabla '{TABLE_NAME}'.")


if __name__ == "__main__":
    upload()
