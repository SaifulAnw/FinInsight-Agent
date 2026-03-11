from sqlalchemy import text
import pandas as pd
from src.ai_agent.config import engine
from src.ai_agent.utils import format_currency

INCOME_CONDITIONS = """
    (
        MUTATION_TYPE = 'CR' 
        OR UPPER(DESCRIPTION) LIKE '%KR OTOMATIS%'
        OR UPPER(DESCRIPTION) LIKE '%SETORAN%'
        OR UPPER(DESCRIPTION) LIKE '%BI-FASTBIF TRANSFER DR%'
    )
    AND DESCRIPTION NOT LIKE '%SALDO AWAL%'
"""

EXPENSE_CONDITIONS = """
    (
        MUTATION_TYPE = 'DB'
        OR UPPER(DESCRIPTION) LIKE '%TRANSAKSI DEBIT%'
        OR UPPER(DESCRIPTION) LIKE '%TRSF E-BANKING%'
        OR UPPER(DESCRIPTION) LIKE '%BIAYA ADM%'
    )
    AND DESCRIPTION NOT LIKE '%BIAYA ADM%'
"""

ADMIN_CONDITIONS = """
    MUTATION_TYPE = 'DB'
    AND (
        UPPER(DESCRIPTION) LIKE '%BIAYA ADM%'
        OR UPPER(DESCRIPTION) LIKE '%ADMIN%'
    )
"""


def get_income(year: int, month: int) -> float:
    # """
    # Get total income for a specific month.

    # Args:
    #     year (int): Year in YYYY format.
    #     month (int): Month number (1-12).

    # Returns:
    #     float: Total income amount for the given month.
    # """
    query = text("""
        SELECT SUM(AMOUNT) FROM transactions 
        WHERE strftime('%Y', DATE) = :year 
        AND strftime('%m', DATE) = :month
        AND (
            MUTATION_TYPE = 'CR' 
            OR DESCRIPTION LIKE '%KR OTOMATIS%'
            OR DESCRIPTION LIKE '%SETORAN%'
            OR DESCRIPTION LIKE '%BI-FASTBIF TRANSFER DR%'
        )
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"year": str(year), "month": f"{month:02d}"}).scalar()

    return float(result or 0)


def get_expenses(year: int, month: int) -> float:
    # """
    # Get total expenses for a specific month.

    # Args:
    #     year (int): Year in YYYY format.
    #     month (int): Month number (1-12).

    # Returns:
    #     float: Total expenses amount for the given month.
    # """
    query = text("""
        SELECT SUM(AMOUNT) FROM transactions 
        WHERE strftime('%Y', DATE) = :year 
        AND strftime('%m', DATE) = :month
        AND (
            MUTATION_TYPE = 'DB'
            OR DESCRIPTION LIKE '%TRANSAKSI DEBIT%'
            OR DESCRIPTION LIKE '%TRSF E-BANKING%'
            OR DESCRIPTION LIKE '%BIAYA ADM%'
        )
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"year": str(year), "month": f"{month:02d}"}).scalar()

    return float(result or 0)


def get_admin_fees(year: int, month: int) -> float:
    # """
    # Get total admin fees for a specific month.

    # Args:
    #     year (int): Year in YYYY format.
    #     month (int): Month number (1-12).

    # Returns:
    #     float: Total admin fees amount for the given month.
    # """
    query = text(f"""
        SELECT COALESCE(SUM(AMOUNT), 0)
        FROM transactions
        WHERE {ADMIN_CONDITIONS}
        AND DATE LIKE :date
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"date": f"{year}-{month:02d}%"}).scalar()

    return float(result or 0)


def get_monthly_summary(year: int, month: int) -> dict:
    """
    Get financial summary for a specific month.

    Args:
        year (int): Year in YYYY format.
        month (int): Month number (1-12).

    Returns:
        dict: Monthly financial summary including income, expense,
              transaction count, and net balance.
    """
    income = get_income(year, month)
    expense = get_expenses(year, month)

    query = text("""
        SELECT COUNT(*)
        FROM transactions
        WHERE DATE LIKE :date
    """)

    with engine.connect() as conn:
        count = conn.execute(query, {"date": f"{year}-{month:02d}%"}).scalar()

    return {
        "income": income,
        "expense": expense,
        "count": int(count or 0),
        "net": income - expense
    }


def compare_months(year1, month1, year2, month2, metric="expense"):
    if metric == "income":
        v1 = get_income(year1, month1)
        v2 = get_income(year2, month2)
        label = "Pemasukan"

    elif metric == "admin":
        v1 = get_admin_fees(year1, month1)
        v2 = get_admin_fees(year2, month2)
        label = "Biaya Admin"

    else:
        v1 = get_expenses(year1, month1)
        v2 = get_expenses(year2, month2)
        label = "Pengeluaran"

    diff = v2 - v1
    percent = (diff / v1 * 100) if v1 != 0 else 0

    return {
        "label": label,
        "month1": v1,
        "month2": v2,
        "diff": diff,
        "percent": percent
    }
    
def get_tracked_period():
    query = text("""
        SELECT MIN(DATE) as start_date, MAX(DATE) as end_date
        FROM transactions
    """)

    with engine.connect() as conn:
        result = conn.execute(query).fetchone()

    return result.start_date, result.end_date

def get_trend_dataframe():
    """
    Return monthly expense trend as DataFrame
    month | expense
    """

    query = text("""
        SELECT 
            strftime('%Y-%m', DATE) as month,
            SUM(AMOUNT) as expense
        FROM transactions
        WHERE (
            MUTATION_TYPE = 'DB'
            OR DESCRIPTION LIKE '%TRANSAKSI DEBIT%'
            OR DESCRIPTION LIKE '%TRSF E-BANKING%'
        )
        GROUP BY month
        ORDER BY month
    """)

    with engine.connect() as conn:
        result = conn.execute(query).fetchall()

    df = pd.DataFrame(result, columns=["month", "expense"])

    return df

def get_latest_transactions(limit: int = 10):
    """
    Get latest transactions from database
    """

    query = text("""
        SELECT 
            DATE,
            DESCRIPTION,
            AMOUNT
        FROM transactions
        ORDER BY DATE DESC
        LIMIT :limit
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"limit": limit}).fetchall()

    df = pd.DataFrame(
        result,
        columns=["date", "description", "amount"]
    )

    return df