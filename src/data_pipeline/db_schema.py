import os
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

# ======================================================
# OFFICIAL SCHEMA
# ======================================================
EXPECTED_COLUMNS = {
    "DATE": "TEXT",
    "DESCRIPTION": "TEXT",
    "AMOUNT": "REAL",
    "MUTATION_TYPE": "TEXT",
    "FINAL_BALANCE": "REAL",
    "SOURCE_FILE": "TEXT",
}


def validate_transactions_schema():
    inspector = inspect(engine)

    if "transactions" not in inspector.get_table_names():
        raise RuntimeError("❌ Table 'transactions' not found in database")

    columns = inspector.get_columns("transactions")

    actual = {col["name"]: str(col["type"]).upper() for col in columns}

    missing = set(EXPECTED_COLUMNS) - set(actual)
    extra = set(actual) - set(EXPECTED_COLUMNS)

    if missing:
        raise RuntimeError(f"❌ Missing columns: {missing}")

    if extra:
        print(f"⚠️ Extra columns detected (ignored): {extra}")

    print("✅ transactions table schema is valid")
    print("Columns:")
    for name in EXPECTED_COLUMNS:
        print(f" - {name} ({actual[name]})")


if __name__ == "__main__":
    validate_transactions_schema()