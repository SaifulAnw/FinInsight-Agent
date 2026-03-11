# trend.py

from sqlalchemy import text
from src.ai_agent.config import engine
from src.ai_agent.metrics import INCOME_CONDITIONS, EXPENSE_CONDITIONS

def get_trend_range(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int
) -> dict:
    """
    Get financial trend data between two months.

    Args:
        start_year (int): Starting year.
        start_month (int): Starting month (1-12).
        end_year (int): Ending year.
        end_month (int): Ending month (1-12).

    Returns:
        dict: Trend data including monthly breakdown and summary totals.
    """

    start_str = f"{start_year}-{start_month:02d}"
    end_str = f"{end_year}-{end_month:02d}"

    query = text(f"""
        SELECT 
            strftime('%Y-%m', DATE) as bulan,
            SUM(CASE 
                WHEN MUTATION_TYPE = 'CR' 
                OR UPPER(DESCRIPTION) LIKE '%KR OTOMATIS%'
                OR UPPER(DESCRIPTION) LIKE '%SETORAN%'
                OR UPPER(DESCRIPTION) LIKE '%BI-FASTBIF TRANSFER DR%'
                THEN AMOUNT ELSE 0 
            END) as pemasukan,
            SUM(CASE 
                WHEN MUTATION_TYPE = 'DB'
                OR UPPER(DESCRIPTION) LIKE '%TRANSAKSI DEBIT%'
                OR UPPER(DESCRIPTION) LIKE '%TRSF E-BANKING%'
                OR UPPER(DESCRIPTION) LIKE '%BIAYA ADM%'
                THEN AMOUNT ELSE 0 
            END) as pengeluaran
        FROM transactions
        WHERE strftime('%Y-%m', DATE) >= :start
          AND strftime('%Y-%m', DATE) <= :end
        GROUP BY bulan
        ORDER BY bulan
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"start": start_str, "end": end_str}).fetchall()

    months = []
    total_income = 0
    total_expense = 0

    for row in rows:
        bulan, pemasukan, pengeluaran = row
        pemasukan = float(pemasukan or 0)
        pengeluaran = float(pengeluaran or 0)
        net = pemasukan - pengeluaran

        months.append({
            "bulan": bulan,
            "income": pemasukan,
            "expense": pengeluaran,
            "net": net
        })

        total_income += pemasukan
        total_expense += pengeluaran

    return {
        "months": months,
        "summary": {
            "total_income": total_income,
            "total_expense": total_expense,
            "net_income": total_income - total_expense
        }
    }