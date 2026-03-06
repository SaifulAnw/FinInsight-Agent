import pdfplumber
import pandas as pd
from pathlib import Path

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
FINAL_HEADER_4_COL = ["DATE", "DESCRIPTION_FULL", "MUTATION", "BALANCE"]
FINAL_DB_COLS = ["DATE", "DESCRIPTION", "AMOUNT", "MUTATION_TYPE",
                 "FINAL_BALANCE", "SOURCE_FILE"]

# ----------------------------------------------------------------------
# Paths (Adjusted for Docker Container)
# ----------------------------------------------------------------------
# Use absolute paths according to volume mounting in docker-compose
INPUT_DIR = Path("/app/data/input")
PROCESSED_DIR = Path("/app/data/processed")

# Ensure output folder exists before saving
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Path for output CSV file
OUT_PATH = PROCESSED_DIR / "all_transactions.csv"

# Column split points (based on the PDF layout)
X_COORDINATES = {
    "DATE_END": 75,        # end of the date column
    "MUTATION_START": 400, # start of the mutation (debit/credit) column
    "BALANCE_START": 500   # start of the balance column
}

# ----------------------------------------------------------------------
# Core processing
# ----------------------------------------------------------------------
def process_single_pdf(pdf_path: Path) -> list:
    """Extract raw rows from a single PDF file."""
    file_name = pdf_path.name
    rows = []

    def extract_page_words(page):
        # Keep only words below the header area (top > 250)
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        page_rows, current_row, last_y = [], [], None

        for w in words:
            if w["top"] < 250:
                continue
            if last_y is not None and abs(w["top"] - last_y) > 5:
                page_rows.append(current_row)
                current_row = []
            current_row.append(w)
            last_y = w["top"]
        if current_row:
            page_rows.append(current_row)

        # Split each row into the four target columns
        for row_words in page_rows:
            if not row_words:
                continue
            row = {col: "" for col in FINAL_HEADER_4_COL}

            for word in row_words:
                txt = word["text"]
                x0 = word["x0"]
                if x0 < X_COORDINATES["DATE_END"]:
                    row["DATE"] = txt
                elif x0 < X_COORDINATES["MUTATION_START"]:
                    row["DESCRIPTION_FULL"] += " " + txt
                elif x0 < X_COORDINATES["BALANCE_START"]:
                    row["MUTATION"] += " " + txt
                else:
                    row["BALANCE"] = txt

            row = {k: v.strip() for k, v in row.items()}
            # Keep only real transaction lines
            if row["DATE"] and "SALDO AWAL" not in row["DESCRIPTION_FULL"].upper():
                rows.append(list(row.values()) + [file_name])

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extract_page_words(page)

    return rows


# ----------------------------------------------------------------------
# Cleaning with pandas
# ----------------------------------------------------------------------
def clean_and_transform(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Convert raw dataframe into a tidy transaction table."""
    # Rename to avoid confusion
    df = df_raw.rename(columns={"MUTATION": "MUTATION_TYPE_RAW",
                               "BALANCE": "FINAL_BALANCE"}).copy()

    # Keep only rows that look like DD/MM
    df = df[df["DATE"].str.match(r"^\d{2}/\d{2}$", na=False)].copy()

    # Separate amount from description
    df["DESCRIPTION"] = df["DESCRIPTION_FULL"].str.replace(r"\s+DB\s*|\s+CR\s*", "", regex=True)

    # First try: pull amount from DESCRIPTION
    df["AMOUNT"] = df["DESCRIPTION"].str.extract(r"(\d{1,3}(?:,\d{3})*\.\d{2})", expand=False)
    df["DESCRIPTION"] = df["DESCRIPTION"].str.replace(r"\d{1,3}(?:,\d{3})*\.\d{2}", "", regex=True).str.strip()

    # Fill missing AMOUNT from the raw mutation column
    trapped = df["MUTATION_TYPE_RAW"].str.extract(r"(\d{1,3}(?:,\d{3})*\.\d{2})", expand=False)
    df["AMOUNT"] = df["AMOUNT"].fillna(trapped)

    # Extract clean mutation type (DB/CR)
    df["MUTATION_TYPE"] = df["MUTATION_TYPE_RAW"].str.extract(r'(DB|CR)', expand=False)

    # Clean numeric strings → float
    def clean_currency(series: pd.Series) -> pd.Series:
        return (series.astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.strip())

    df["AMOUNT"] = clean_currency(df["AMOUNT"])
    df["FINAL_BALANCE"] = clean_currency(df["FINAL_BALANCE"])

    df["AMOUNT"] = pd.to_numeric(df["AMOUNT"], errors="coerce")
    df["FINAL_BALANCE"] = pd.to_numeric(df["FINAL_BALANCE"], errors="coerce")

    # Add year from source file name and parse dates
    df["YEAR"] = df["SOURCE_FILE"].str.extract(r"(\d{4})").astype(str)
    df["DATE"] = pd.to_datetime(df["DATE"] + "/" + df["YEAR"],
                                format="%d/%m/%Y", errors="coerce")

    # Drop helper columns
    df.drop(columns=["DESCRIPTION_FULL", "MUTATION_TYPE_RAW", "YEAR"],
            inplace=True)

    return df[[c for c in FINAL_DB_COLS if c in df.columns]]


# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # -------------------------------------------------
    # 1️⃣  Gather and sort PDF files
    # -------------------------------------------------
    pdf_files = list(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No PDF files found in {INPUT_DIR}")
        raise SystemExit

    # Mapping of month abbreviations to numbers for sorting
    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
    }

    pdf_files.sort(key=lambda p: (
        int(p.stem.rsplit('-', 1)[-1]),   # year (YYYY)
        month_map[p.stem.split('-')[0].capitalize()]   # month (MMM)
    ))

    # -------------------------------------------------
    # 2️⃣  Parse all PDFs
    # -------------------------------------------------
    all_rows = []
    print(f"Parsing {len(pdf_files)} file(s)...")
    for p in pdf_files:
        print(f" → {p.name}")
        all_rows.extend(process_single_pdf(p))

    # -------------------------------------------------
    # 3️⃣  Build DataFrames and clean
    # -------------------------------------------------
    df_raw = pd.DataFrame(all_rows, columns=FINAL_HEADER_4_COL + ["SOURCE_FILE"])
    df_final = clean_and_transform(df_raw)

    # -------------------------------------------------
    # 4️⃣  Report & save
    # -------------------------------------------------
    print("\n=============================================")
    print(f"Parsing complete – {len(df_final)} transactions extracted.")
    print("First 5 rows:")
    print(df_final.head())
    print("Data types:")
    print(df_final.dtypes)
    print("=============================================")

    # Save extraction results to processed folder
    df_final.to_csv(OUT_PATH, index=False)
    print(f"\n✅ Saved to {OUT_PATH}")