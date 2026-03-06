import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text, Engine
from db_schema import validate_transactions_schema

# ----------------------------------------------------------------------
# Paths (Adjusted for Docker Container)
# ----------------------------------------------------------------------
DB_PATH = Path("/app/data/database/financial_data.db")
CSV_PATH = Path("/app/data/processed/all_transactions.csv")

# Ensure the database directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------
# Table schema
# ----------------------------------------------------------------------
TABLE_NAME = "transactions"

# ----------------------------------------------------------------------
# Load function
# ----------------------------------------------------------------------
def load_data_to_sqlite(csv_path: Path, db_path: Path, table_name: str) -> None:
    """Load the cleaned CSV into a SQLite database."""
    db_uri = f"sqlite:///{db_path}"
    print(f"Loading data from {csv_path.name} into {db_uri}...")

    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return

    engine: Engine = create_engine(db_uri, echo=False)
    df = pd.read_csv(csv_path)
    df['FINAL_BALANCE'] = df['FINAL_BALANCE'].ffill()

    try:
        with engine.connect() as conn:
            # Drop the old table if it exists
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            conn.commit()
            print(f"Old table '{table_name}' dropped (if it existed).")

            # Write the DataFrame to SQLite
            df.to_sql(table_name, con=conn, if_exists="replace", index=False)
            conn.commit()

            # Verify row count
            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"Successfully loaded {row_count} rows into '{table_name}'.")

    except Exception as e:
        print(f"An error occurred while loading data: {e}")


# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
if __name__ == "__main__":
    load_data_to_sqlite(CSV_PATH, DB_PATH, TABLE_NAME)
    try:
        print("\n🔍 Validating database schema...")
        validate_transactions_schema()
        print("✅ ETL (Load) phase complete and verified!")
    except Exception as e:
        print(f"❌ Schema validation failed: {e}")