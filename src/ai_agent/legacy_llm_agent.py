import os
import re
import logging
import locale
import cursor
from datetime import datetime, time
from dotenv import load_dotenv
import requests
from functools import lru_cache
from sqlalchemy.pool import QueuePool
from sqlalchemy import create_engine, inspect, text
from utils import format_currency, shift_month, format_trend_report

from smolagents import tool, CodeAgent, OpenAIServerModel

# ======================================================
# 1. LOAD CONFIGURATION
# ======================================================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

# Model mapping from .env
MODELS = {
    "logic": os.getenv("OLLAMA_MODEL"),          # qwen2.5-coder
    "reasoning": os.getenv("OLLAMA_REASON_MODEL"), # phi3
    "chat": os.getenv("OLLAMA_CHAT_MODEL")         # mistral
}

requests_timeout = 60.0

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10
)

def test_ollama_connection(model_name):
    """Test specific connection for a given model."""
    try:
        base_url = OLLAMA_BASE_URL.replace('/v1', '').rstrip('/')
        response = requests.post(
            f"{base_url}/api/generate",
            json={"model": model_name, "prompt": "Hi", "stream": False},
            timeout=60 
        )
        return response.status_code == 200
    except:
        return False

# Check all models on startup
print("🚀 Initializing Multi-Model System...")
for key, name in MODELS.items():
    status = "✅" if test_ollama_connection(name) else "❌"
    print(f"{status} {key.capitalize()} Model: {name}")
    
def route(name: str):
    print(f"🧭 ROUTE → {name}")
    
# ======================================================
# GLOBAL CONSTANTS FOR FINANCIAL CRITERIA
# ======================================================
INCOME_CONDITIONS = """
    MUTATION_TYPE = 'CR'
    AND DESCRIPTION NOT LIKE '%SALDO AWAL%'
"""

EXPENSE_CONDITIONS = """
    MUTATION_TYPE = 'DB'
    AND DESCRIPTION NOT LIKE '%BIAYA ADM%'
"""

ADMIN_CONDITIONS = """
    MUTATION_TYPE = 'DB'
    AND (
        UPPER(DESCRIPTION) LIKE '%BIAYA ADM%'
        OR UPPER(DESCRIPTION) LIKE '%ADMIN%'
    )
"""

    

def build_date_filter(year: int, month: int | None = None, relative_range=None) -> str:
    """Universal version for all date filter needs."""
    if relative_range:
        y1, m1, y2, m2 = relative_range
        return f"DATE BETWEEN '{y1:04d}-{m1:02d}-01' AND '{y2:04d}-{m2:02d}-31'"
    if month:
        return f"DATE LIKE '{year:04d}-{month:02d}%'"
    return f"strftime('%Y', DATE) = '{year:04d}'"

# Set up logging
logging.basicConfig(filename='sql_queries.log', level=logging.INFO)

ALLOWED_COLUMNS = {'DATE', 'DESCRIPTION', 'AMOUNT', 'MUTATION_TYPE', 'FINAL_BALANCE', 'SOURCE_FILE'}
    
def format_monthly_summary(year, month, summary: dict) -> str:
    month_name = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ][month]

    net_label = "Surplus" if summary["net"] >= 0 else "Defisit"

    return f"""
📊 Ringkasan Keuangan — {month_name} {year}

Total Pemasukan   : {format_currency(summary['income'])}
Total Pengeluaran: {format_currency(summary['expense'])}
Saldo Bersih     : {format_currency(abs(summary['net']))} ({net_label})
Jumlah Transaksi : {summary['count']}
""".strip()


# Extract column names from query and validate
def validate_columns(query):
    # Find the part between SELECT and FROM
    match = re.search(r'SELECT\s+(.*?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
    if not match:
        return True, ""

    columns_text = match.group(1)

    # Forbid SELECT *
    if re.search(r'\bSELECT\s+\*', query, re.IGNORECASE):
        return False, "SELECT * is forbidden"

    # Whitelisted SQL functions
    sql_functions = {
        'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
        'COALESCE', 'STRFTIME'
    }

    # Allowed SQL keywords (non-column)
    sql_keywords = {
    'AS', 'DISTINCT', 'TOTAL', 'COUNT'
    }

    # Validate each column expression
    for col in columns_text.split(','):
        col = col.strip().upper()

        # Extract all SQL-like tokens
        tokens = re.findall(r'\b[A-Z_]+\b', col)

        for token in tokens:
            # Skip SQL keywords
            if token in sql_keywords:
                continue

            # Allow SQL functions
            if token in sql_functions:
                continue

            # Allow whitelisted columns
            if token in ALLOWED_COLUMNS:
                continue

            # Allow COUNT(*)
            if token == '*':
                continue

            return False, f"Column '{token}' is not allowed"

    return True, ""

# ======================================================
# 2. TABLE DESCRIPTION
# ======================================================
def get_table_description() -> str:
    try:
        inspector = inspect(engine)
        cols = inspector.get_columns("transactions")
        col_desc = "\n".join([f"- {c['name']} ({c['type']})" for c in cols])
    except:
        col_desc = "- DATE, DESCRIPTION, AMOUNT, MUTATION_TYPE, FINAL_BALANCE, SOURCE_FILE"

    return f"""
            You are a Financial Data Expert.
            Table Name: 'transactions'

            COLUMNS AVAILABLE IN DATABASE:
            {col_desc}
            
            CRITICAL GLOBAL CONSTANTS (USE THESE FOR ALL QUERIES):
            
            # INCOME CONDITIONS:
            {INCOME_CONDITIONS}
            
            # EXPENSE CONDITIONS:
            {EXPENSE_CONDITIONS}
            
            IMPORTANT RULES:
            1. Use these SAME conditions for ALL income/expense calculations
            2. AMOUNT is stored as FLOAT (no cleaning needed)
            3. Date format: Use DATE LIKE '2024-11%' for November 2024
            
            CORRECT QUERY EXAMPLES:
            1. Total income November 2024: 
               SELECT SUM(AMOUNT) FROM transactions 
               WHERE {INCOME_CONDITIONS}
               AND DATE LIKE '2024-11%'
            
            2. Monthly trend: 
               SELECT strftime('%Y-%m', DATE) as bulan,
                      SUM(CASE WHEN {INCOME_CONDITIONS} THEN AMOUNT ELSE 0 END) as pemasukan,
                      SUM(CASE WHEN {EXPENSE_CONDITIONS} THEN AMOUNT ELSE 0 END) as pengeluaran
               FROM transactions 
               GROUP BY bulan ORDER BY bulan
            """

# def timeout_decorator(timeout_seconds):
#     def decorator(func):
#         @functools.wraps(func)
#         def wrapper(*args, **kwargs):
#             result = [None]
#             exception = [None]
            
#             def target():
#                 try:
#                     result[0] = func(*args, **kwargs)
#                 except Exception as e:
#                     exception[0] = e
            
#             thread = threading.Thread(target=target)
#             thread.daemon = True
#             thread.start()
#             thread.join(timeout_seconds)
            
#             if thread.is_alive():
#                 raise TimeoutError(f"Query exceeded {timeout_seconds} second limit")
            
#             if exception[0]:
#                 raise exception[0]
            
#             return result[0]
#         return wrapper
#     return decorator

@tool
def get_current_year() -> dict:
    """
    Get current year and month for date context.
    
    Returns:
        dict: Current date information with keys:
            - current_year (int): Current year
            - current_month (int): Current month (1-12)
            - current_month_name (str): Month name in English
    """
    now = datetime.now()
    return {
        "current_year": now.year,
        "current_month": now.month,
        "current_month_name": now.strftime("%B")
    }

# ======================================================
# 3. SQL TOOL
# ======================================================
@tool
# @timeout_decorator(timeout_seconds=30) # Optional: Uncomment to enable timeout
def sql_engine(query: str) -> str:
    """
    Execute a SAFE SQL query against the transactions table.
    
    Args:
        query: The SQL query to execute. It must be a SELECT statement.
    
    STRICT RULES ENFORCED:
    1. Only SELECT queries allowed
    2. SELECT * is strictly forbidden
    3. Must reference transactions table
    4. Auto LIMIT 100 (override with explicit LIMIT ≤ 500)
    5. No dangerous operations (DROP, DELETE, etc.)
    6. Maximum 500 rows returnable
    
    IMPORTANT: AMOUNT field is stored as FLOAT/REAL (numeric).
    No need for clean_amount() conversions.
    
    Example valid queries:
    - SELECT DATE, DESCRIPTION, AMOUNT FROM transactions WHERE DESCRIPTION LIKE '%ADMIN%'
    - SELECT SUM(AMOUNT) as total FROM transactions WHERE DATE LIKE '2024-11%'
    - SELECT COUNT(*) as count FROM transactions
    """
    
    logging.info(f"SQL Query: {query}")
    
    # ========= SECURITY VALIDATION ==========
    is_valid, error_msg = validate_columns(query)
    if not is_valid:
        return f"Security Error: {error_msg}"

    query = query.strip()
    q_upper = query.upper()
    
    # ========== COMPREHENSIVE VALIDATION ==========
    
    # 1. Only SELECT queries allowed
    if not q_upper.startswith("SELECT"):
        return "SQL Execution Error: Only SELECT queries are allowed. Received: " + query[:50] + "..."
    
    # 2. Strictly forbid SELECT *
    if re.search(r'SELECT\s+\*', q_upper):
        return "SQL Execution Error: SELECT * is forbidden. You must specify columns explicitly. Example: SELECT DATE, DESCRIPTION, AMOUNT FROM transactions"
    
    # 3. Must reference transactions table
    if not re.search(r'\bFROM\s+TRANSACTIONS\b', q_upper):
        return "SQL Execution Error: Query must reference 'transactions' table using FROM transactions."
    
    # 4. Block dangerous operations
    dangerous_patterns = [
        (r'\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE)\b', 'data manipulation'),
        (r'\b(EXEC|EXECUTE|SHUTDOWN|GRANT|REVOKE)\b', 'system operations'),
        (r'--|\/\*', 'SQL comments'),
    ]
    
    for pattern, operation in dangerous_patterns:
        if re.search(pattern, q_upper):
            return f"SQL Execution Error: {operation} are not allowed in queries."
    
    # 5. Optional: Prevent complex queries
    complex_patterns = [
        r'\bJOIN\b.*\bJOIN\b',
        r'\bUNION\b',
    ]
    
    for pattern in complex_patterns:
        if re.search(pattern, q_upper):
            return "SQL Execution Error: Complex queries with multiple JOINs, subqueries, or UNION are not allowed. Keep queries simple."
    
    # ========== INTELLIGENT LIMIT MANAGEMENT ==========
    
    # Check for existing LIMIT clause
    limit_match = re.search(r'\bLIMIT\s+(\d+)', q_upper)
    
    if limit_match:
        user_limit = int(limit_match.group(1))
        if user_limit > 500:
            return "SQL Execution Error: Maximum allowed LIMIT is 500 rows."
        elif user_limit == 0:
            return "SQL Execution Error: LIMIT 0 is not allowed."
        
        final_query = query
        limit_info = f"User-specified LIMIT: {user_limit}"
    else:
        clean_query = query.rstrip(';')
        final_query = f"{clean_query} LIMIT 100"
        limit_info = "Auto-applied LIMIT: 100"
    
    # ========== SAFE EXECUTION ==========
    
    try:
        with engine.connect() as con:
            # Execute the safe query
            result = con.execute(text(final_query))
            columns = result.keys()
            
            # Fetch with buffer
            rows = result.fetchmany(101)
            
            # Build output
            output = " | ".join(columns) + "\n"
            output += "-" * (len(" | ".join(columns))) + "\n"
            
            displayed_rows = 0
            for row in rows[:100]:
                output += " | ".join(str(value) if value is not None else "NULL" for value in row) + "\n"
                displayed_rows += 1
            
            # Add footer
            output += f"\n{'='*60}\n"
            output += f"ROWS RETURNED: {displayed_rows}\n"
            output += f"QUERY MODE: {limit_info}\n"
            
            if len(rows) > 100:
                output += f"WARNING: More rows exist ({len(rows)-1}+ total). Use LIMIT N for precise control.\n"
            
            output += f"{'='*60}"
            
            return output
    
    except Exception as e:
        error_msg = str(e).lower()
        
        # Self-Healing for Incorrect Column Names
        if "no such column" in error_msg:
            inspector = inspect(engine)
            columns = [c['name'] for c in inspector.get_columns("transactions")]
            column_list = ", ".join(columns)
            
            return (f"SQL Execution Error: Column not found. "
                    f"Available columns are: [{column_list}]. "
                    f"Please use DESCRIPTION for filtering keywords and correct your column names.")
        
        # Self-Healing for SQL Syntax Errors
        elif "syntax error" in error_msg or "near" in error_msg:
            return (f"SQL Execution Error: There is a syntax error in your SQL. "
                    f"Details: {str(e)}. Please rewrite the query with correct SQL syntax.")
        
        # General fallback
        else:
            return f"SQL Execution Error: {str(e)}"
        

@tool
def suggest_query(question: str) -> str:
    """
    Suggest SQL query for a financial question.
    
    Args:
        question: User's question in natural language
    
    Returns:
        str: Suggested SQL query and notes.
    """
    suggestions = {
        "admin": {
            "pattern": ["admin", "biaya admin", "biaya administrasi"],
            "query": f"SELECT SUM(AMOUNT) FROM transactions WHERE DESCRIPTION LIKE '%BIAYA ADM%' AND DATE LIKE 'YYYY-MM%'",
            "notes": "Ganti YYYY-MM dengan tahun-bulan yang diminta"
        },
        "pemasukan": {
            "pattern": ["pemasukan", "income", "setoran", "kredit"],
            "query": f"SELECT SUM(AMOUNT) FROM transactions WHERE {INCOME_CONDITIONS} AND DATE LIKE 'YYYY-MM%'",
            "notes": "Menggunakan income conditions yang konsisten"
        },
        "pengeluaran": {
            "pattern": ["pengeluaran", "expense", "debit", "keluar"],
            "query": f"SELECT SUM(AMOUNT) FROM transactions WHERE {EXPENSE_CONDITIONS} AND DATE LIKE 'YYYY-MM%'",
            "notes": "Menggunakan expense conditions yang konsisten"
        }
    }
    
    question_lower = question.lower()
    
    for category, info in suggestions.items():
        for pattern in info["pattern"]:
            if pattern in question_lower:
                return f"Suggested query for '{category}':\n{info['query']}\n\nNote: {info['notes']}"
    
    return "No specific suggestion. Remember to use DATE LIKE 'YYYY-MM%' for monthly filters."

# ======================================================
# 4. PARSER TOOL
# ======================================================
@tool
def parse_sql_result(result_string: str) -> list:
    """
    Parse output from sql_engine into a list of rows.

    Args:
        result_string: The raw string returned by sql_engine,
            including a header row and pipe-separated values.

    Returns:
        list: A list of rows (list of strings), excluding the header.
    """
    if not result_string or "SQL Execution Error" in result_string:
        return []
    
    try:
        lines = result_string.strip().split("\n")
        if len(lines) < 2:  # Must have at least header and one data line
            return []
        
        # Skip header and separator
        data_lines = []
        for line in lines[2:]:  # Skip first two lines
            if line.strip() and not line.startswith('='):  # Skip footer lines
                data_lines.append(line.split(" | "))
        
        return data_lines
    except Exception as e:
        logging.error(f"Error parsing SQL result: {e}")
        return []


def get_admin_fees(year: int, month: int | None = None, relative_range=None) -> str:
    date_filter = build_date_filter(year, month, relative_range)

    query = f"""
    SELECT COALESCE(SUM(AMOUNT), 0)
    FROM transactions
    WHERE {ADMIN_CONDITIONS}
    AND {date_filter}
    """

    result = sql_engine(query)
    parsed = parse_sql_result(result)

    total = 0.0
    if parsed and parsed[0] and parsed[0][0] not in (None, "NULL", ""):
        total = float(parsed[0][0])

    return format_currency(total)


# ======================================================
# 4. MONTHLY REPORT TOOL
# ======================================================
@tool
def monthly_report(year: int, month: int) -> str:
    """
    Menghasilkan laporan keuangan bulanan lengkap termasuk pemasukan, pengeluaran, dan saldo.
    
    Args:
        year: Tahun dalam format angka (contoh: 2024).
        month: Bulan dalam format angka 1-12 (contoh: 1 untuk Januari).
    """
    month_str = f"{month:02d}"
    
    with engine.connect() as con:
        income = con.execute(text(f"""
            SELECT COALESCE(SUM(AMOUNT), 0)
            FROM transactions
            WHERE {INCOME_CONDITIONS}
              AND strftime('%Y', DATE) = :year
              AND strftime('%m', DATE) = :month
        """), {"year": str(year), "month": month_str}).scalar()

        expense = con.execute(text(f"""
            SELECT COALESCE(SUM(AMOUNT), 0)
            FROM transactions
            WHERE {EXPENSE_CONDITIONS}
              AND strftime('%Y', DATE) = :year
              AND strftime('%m', DATE) = :month
        """), {"year": str(year), "month": month_str}).scalar()

        balance = con.execute(text("""
            SELECT FINAL_BALANCE
            FROM transactions
            WHERE strftime('%Y', DATE) = :year
              AND strftime('%m', DATE) = :month
              AND FINAL_BALANCE IS NOT NULL
            ORDER BY DATE DESC
            LIMIT 1
        """), {"year": str(year), "month": month_str}).scalar()

    return {
        "year": year,
        "month": month,
        "total_income": float(income) if income else 0.0,
        "total_expense": float(expense) if expense else 0.0,
        "ending_balance": float(balance) if balance is not None else None
    }


@tool
def compare_months(month1: int, year1: int, month2: int, year2: int) -> str:
    """
    Compare financial performance between two specific months.
    
    Args:
        month1: The first month to compare (1-12).
        year1: The year of the first month (e.g., 2024).
        month2: The second month to compare (1-12).
        year2: The year of the second month (e.g., 2024).
    
    Returns:
        str: Comparison result with difference and status.
    """
    # Take the first month's data
    data1 = monthly_report(year1, month1)
    # Take the second month's data
    data2 = monthly_report(year2, month2)
    
    # Retrieve ending balance (default 0 if None)
    bal1 = data1.get('ending_balance') or 0
    bal2 = data2.get('ending_balance') or 0
    
    diff = bal1 - bal2
    status = "up" if diff > 0 else "down"

    return f"Balance Comparison: {month1}/{year1} vs {month2}/{year2}. Difference: Rp {abs(diff):,.2f} ({status})."

def extract_year_month(question: str) -> dict:
    """
    Ekstrak tahun dan bulan dari pertanyaan pengguna untuk filter database.
    Mendukung:
    - Bulan spesifik: 'Januari 2025'
    - Rentang bulan: 'Januari-Maret 2025'
    - Durasi relatif: '3 bulan terakhir', '6 bulan terakhir'
    """
    
    # Normalisasi
    question_lower = question.lower().replace("–", "-").replace("—", "-")
    
    # Normalisasi singkatan bulan
    month_abbr = {
        'jan': 'januari', 'feb': 'februari', 'mar': 'maret',
        'apr': 'april', 'mei': 'mei', 'jun': 'juni',
        'jul': 'juli', 'agu': 'agustus', 'ags': 'agustus',
        'sep': 'september', 'okt': 'oktober', 'nov': 'november',
        'des': 'desember'
    }
    
    for abbr, full in month_abbr.items():
        question_lower = re.sub(rf'\b{abbr}\b', full, question_lower)
    
    month_map = {
        'januari': 1, 'februari': 2, 'maret': 3, 'april': 4,
        'mei': 5, 'juni': 6, 'juli': 7, 'agustus': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'desember': 12
    }
    
    # 1. Cek DURASI RELATIF terlebih dahulu (prioritas tinggi)
    # Pattern: 'X bulan terakhir' atau 'terakhir X bulan'
    duration_match = re.search(r'(\d+)\s*bulan\s*terakhir|terakhir\s*(\d+)\s*bulan', question_lower)
    if duration_match:
        month_count = int(duration_match.group(1) or duration_match.group(2))
        
        # Ambil tahun dan bulan dari data terbaru di database
        earliest_date, latest_date = get_data_range()
        if latest_date:
            latest_dt = datetime.strptime(latest_date[:10], "%Y-%m-%d")
            end_year = latest_dt.year
            end_month = latest_dt.month
            
            # Hitung bulan awal berdasarkan durasi
            start_year = end_year
            start_month = end_month - (month_count - 1)
            
            while start_month < 1:
                start_year -= 1
                start_month += 12
            
            return {
                "year": start_year,
                "month": start_month,
                "month_name": list(month_map.keys())[start_month-1].capitalize(),
                "end_year": end_year,
                "end_month": end_month,
                "is_range": True,
                "is_relative_duration": True,
                "duration_months": month_count
            }
    
    # 2. Extract Year
    year_match = re.search(r'(20\d{2})', question_lower)
    year = int(year_match.group(1)) if year_match else None
    
    # 3. Extract Months
    found_months = []
    for name, num in month_map.items():
        if re.search(rf'\b{name}\b', question_lower):
            for match in re.finditer(rf'\b{name}\b', question_lower):
                found_months.append((match.start(), num, name.capitalize()))
    
    found_months.sort()  # Sort by position in text
    
    # TENTUKAN RESULT DICT BERDASARKAN LOGIKA PARSING
    result = {}
    
    # Jika ada range bulan
    if len(found_months) >= 2:
        start_year = year if year else datetime.now().year
        end_year = start_year
        
        # Handle cross-year: jika bulan akhir < bulan awal, tambah tahun
        if found_months[-1][1] < found_months[0][1]:
            end_year += 1
        
        result = {
            "year": start_year,
            "month": found_months[0][1],
            "month_name": found_months[0][2],
            "end_year": end_year,
            "end_month": found_months[-1][1],
            "is_range": True,
            "is_relative_duration": False
        }
    
    # Jika hanya satu bulan
    elif found_months:
        result = {
            "year": year if year else datetime.now().year,
            "month": found_months[0][1],
            "month_name": found_months[0][2],
            "is_range": False,
            "is_relative_duration": False
        }
    
    # Jika hanya tahun tanpa bulan
    elif year:
        result = {
            "year": year,
            "month": 1,  # Default Januari
            "month_name": "Januari",
            "end_year": year,
            "end_month": 12,  # Default Desember
            "is_range": True,
            "is_full_year": True,
            "is_relative_duration": False
        }
    
    # Default: bulan dan tahun sekarang
    else:
        current = datetime.now()
        result = {
            "year": current.year,
            "month": current.month,
            "month_name": list(month_map.keys())[current.month-1].capitalize(),
            "is_range": False,
            "is_relative_duration": False
        }
    
    # ============================================
    # BOUNDS CHECKING: CLAMP TO AVAILABLE DATA
    # ============================================
    _, latest_date = get_data_range()
    if latest_date:
        latest_dt = datetime.strptime(latest_date[:10], "%Y-%m-%d")
        max_year = latest_dt.year
        max_month = latest_dt.month
    else:
        max_year = datetime.now().year
        max_month = datetime.now().month
    
    # Clamp tahun dan bulan ke data yang tersedia
    if result.get("year", 0) > max_year:
        result["year"] = max_year
        if result.get("month", 0) > max_month:
            result["month"] = max_month
    
    elif result.get("year", 0) == max_year and result.get("month", 0) > max_month:
        result["month"] = max_month
    
    # Clamp end_year dan end_month juga jika ada
    if result.get("end_year", 0) > max_year:
        result["end_year"] = max_year
        if result.get("end_month", 0) > max_month:
            result["end_month"] = max_month
    
    elif result.get("end_year", 0) == max_year and result.get("end_month", 0) > max_month:
        result["end_month"] = max_month
    
    # Update month_name jika month berubah
    if result.get("month"):
        result["month_name"] = list(month_map.keys())[result["month"] - 1].capitalize()
    
    return result


def get_latest_year_for_month(month: int) -> int:
    with engine.connect() as con:
        result = con.execute(text("""
            SELECT MAX(strftime('%Y', DATE))
            FROM transactions
            WHERE strftime('%m', DATE) = :month
        """), {"month": f"{month:02d}"}).scalar()
    return int(result) if result else datetime.now().year
    

# ======================================================
# 5. AGENT INITIALIZATION
# ======================================================
def initialize_agent() -> CodeAgent:
    print(f"✅ Database: {DATABASE_URL}")
    
    # Use logic model (Qwen) for Main Agent
    logic_model_name = MODELS["logic"]
    
    print(f"🧠 Loading Main Agent Logic with: {logic_model_name}")
    
    clean_base_url = OLLAMA_BASE_URL.split('/v1')[0]

    model = OpenAIServerModel(
        model_id=logic_model_name,
        api_base=clean_base_url + "/v1",
        api_key="dummy",
    )

    agent = CodeAgent(
        tools=[
            sql_engine, 
            parse_sql_result, 
            monthly_report, 
            compare_months, 
            get_current_year,
            suggest_query
        ],
        model=model,
        description=get_table_description(),
        max_steps=10,
        additional_authorized_imports=["datetime", "re", "locale"]
    )

    return agent


def get_income(year: int, month: int | None, relative_range=None) -> str:
    date_filter = build_date_filter(year, month, relative_range)
    query = f"""
    SELECT COALESCE(SUM(AMOUNT), 0)
    FROM transactions
    WHERE {INCOME_CONDITIONS}
    AND {date_filter}
    """

    result = sql_engine(query)
    parsed = parse_sql_result(result)

    total = 0.0
    if parsed and parsed[0] and parsed[0][0] not in (None, "NULL", ""):
        total = float(parsed[0][0])

    return format_currency(total)


def get_expenses(year: int, month: int | None, relative_range=None) -> str:
    date_filter = build_date_filter(year, month, relative_range)
    query = f"""
    SELECT COALESCE(SUM(AMOUNT), 0)
    FROM transactions
    WHERE {EXPENSE_CONDITIONS}
    AND {date_filter}
    """

    result = sql_engine(query)
    parsed = parse_sql_result(result)

    total = 0.0
    if parsed and parsed[0] and parsed[0][0] not in (None, "NULL", ""):
        total = float(parsed[0][0])

    return format_currency(total)

def get_monthly_summary(year: int, month: int) -> dict:
    # INCOME
    income_query = f"""
    SELECT COALESCE(SUM(AMOUNT), 0)
    FROM transactions
    WHERE {INCOME_CONDITIONS}
    AND DATE LIKE '{year:04d}-{month:02d}%'
    """

    # EXPENSE
    expense_query = f"""
    SELECT COALESCE(SUM(AMOUNT), 0)
    FROM transactions
    WHERE {EXPENSE_CONDITIONS}
    AND DATE LIKE '{year:04d}-{month:02d}%'
    """

    income_raw = parse_sql_result(sql_engine(income_query))
    expense_raw = parse_sql_result(sql_engine(expense_query))

    income = float(income_raw[0][0]) if income_raw and income_raw[0][0] not in (None, "NULL", "") else 0
    expense = float(expense_raw[0][0]) if expense_raw and expense_raw[0][0] not in (None, "NULL", "") else 0

    # Count total transactions
    count_query = f"""
    SELECT COUNT(*)
    FROM transactions
    WHERE DATE LIKE '{year:04d}-{month:02d}%'
    """

    result = sql_engine(count_query)
    parsed = parse_sql_result(result)

    count = int(parsed[0][0]) if parsed and parsed[0] else 0

    return {
        "income": income,
        "expense": expense,
        "count": count,
        "net": income - expense
    }


def get_data_range():
    """Get earliest and latest date from transactions table directly."""
    query = text("SELECT MIN(DATE), MAX(DATE) FROM transactions")
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query).fetchone()
            
            # Jika ada data, kembalikan nilai aslinya
            if result and result[0] and result[1]:
                return result[0], result[1]
        
        # Jika database kosong/tabel tidak ada
        logging.warning("Database transactions kosong.")
        return None, None 
            
    except Exception as e:
        logging.error(f"Error koneksi database: {e}")
        return None, None
    
    
    
def get_trend_bulk(start_year: int, start_month: int, end_year: int, end_month: int):
    """Get trend data for a range of months."""
    try:
        start_str = f"{start_year}-{start_month:02d}"
        end_str = f"{end_year}-{end_month:02d}"
        
        query = text(f"""
        SELECT 
            strftime('%Y-%m', DATE) as bulan,
            SUM(CASE WHEN {INCOME_CONDITIONS} THEN AMOUNT ELSE 0 END) as pemasukan,
            SUM(CASE WHEN {EXPENSE_CONDITIONS} THEN AMOUNT ELSE 0 END) as pengeluaran
        FROM transactions
        WHERE strftime('%Y-%m', DATE) >= :start 
          AND strftime('%Y-%m', DATE) <= :end
        GROUP BY bulan
        ORDER BY bulan
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {"start": start_str, "end": end_str})
            rows = result.fetchall()
        
        if not rows:
            print(f"📊 No data found for period: {start_str} to {end_str}")
            return []
            
        return rows

    except Exception as e:
        print(f"❌ Error in get_trend_bulk: {e}")
        return []
        


@lru_cache(maxsize=32)
def cached_monthly_summary(year: int, month: int) -> dict:
    time.sleep(0.1)  # Simulate slow query
    return get_monthly_summary(year, month)

def detect_compare_metric(q: str) -> str:
    if any(k in q for k in ['admin', 'administrasi', 'biaya admin']):
        return 'admin'
    if any(k in q for k in ['pemasukan', 'income', 'masuk']):
        return 'income'
    return 'expense'  # default


# ======================================================
# 6. RUN QUERY SAFELY
# ======================================================
def ask(agent: CodeAgent, question: str, debug_mode: bool = False):
    print(f"\n🧠 Question: {question}")
    print("-" * 60)

    q = question.lower()
    
    analyst_keywords = [
        'analisa', 'analisis', 'jelaskan', 'kenapa',
        'evaluasi', 'insight', 'pola', 'tren', 'trend'
    ]
    is_analyst_intent = any(k in q for k in analyst_keywords)

    # ==================================================
    # 1. DATA RANGE VALIDATION
    # ==================================================
    earliest_date, latest_date = get_data_range()
    if not latest_date:
        print("❌ Database kosong atau tidak terbaca.")
        return

    latest_dt = datetime.strptime(latest_date[:10], "%Y-%m-%d")
    data_year, data_month = latest_dt.year, latest_dt.month

    # ==================================================
    # 2. TIME EXTRACTION (DENGAN PERBAIKAN)
    # ==================================================
    time_info = extract_year_month(question)
    year = time_info["year"]
    month = time_info["month"]
    end_month = time_info.get("end_month")
    is_range = time_info.get("is_range", False)

    if debug_mode:
        print(f"🔍 Parsed time: {time_info}")

    # ==================================================
    # 3. EXPLICIT MONTH-TO-MONTH COMPARISON (HIGHEST PRIORITY)
    # ==================================================
    # PATCH 1: Compare dengan tahun di kedua bulan
    compare_match = re.search(
        r'bandingkan.*?(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(20\d{2}).*?(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(20\d{2})',
        q
    )

    # PATCH 2: Compare tanpa tahun (bulan pertama tanpa tahun)
    compare_no_year = None
    if not compare_match:
        compare_no_year = re.search(
            r'bandingkan.*?(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+dan\s+(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(20\d{2})',
            q
        )

    if compare_match or compare_no_year:
        if compare_match:
            m1, y1, m2, y2 = compare_match.groups()
        else:  # compare_no_year
            m1, m2, y = compare_no_year.groups()
            y1 = y2 = y
        
        month_map = {
            'januari':1,'februari':2,'maret':3,'april':4,
            'mei':5,'juni':6,'juli':7,'agustus':8,
            'september':9,'oktober':10,'november':11,'desember':12
        }

        metric = detect_compare_metric(q)
        route(f"P1_COMPARE_{metric.upper()}")

        if metric == 'admin':
            v1 = get_admin_fees(int(y1), month_map[m1])
            v2 = get_admin_fees(int(y2), month_map[m2])
            label = "Biaya admin"

        elif metric == 'income':
            v1 = get_income(int(y1), month_map[m1])
            v2 = get_income(int(y2), month_map[m2])
            label = "Pemasukan"

        else:  # expense
            v1 = get_expenses(int(y1), month_map[m1])
            v2 = get_expenses(int(y2), month_map[m2])
            label = "Pengeluaran"

        diff = v2 - v1
        percent_change = (diff / v1 * 100) if v1 != 0 else 0
        
        print(f"\n📊 Perbandingan {label}:")
        print(f"✅ {m1.capitalize()} {y1}: Rp {v1:,.2f}")
        print(f"✅ {m2.capitalize()} {y2}: Rp {v2:,.2f}")
        print(f"📈 Perubahan: Rp {diff:+,.2f} ({percent_change:+.1f}%)")
        return
    
    # ==================================================
    # 4. INVALID MIXED COMPARISON
    # ==================================================
    if "bandingkan" in q and any(k in q for k in ["admin", "pengeluaran", "pemasukan"]):
        metrics = []
        if "admin" in q or "biaya admin" in q:
            metrics.append("admin")
        if "pengeluaran" in q or "expense" in q or "keluar" in q:
            metrics.append("expense")
        if "pemasukan" in q or "income" in q or "masuk" in q:
            metrics.append("income")

        if len(set(metrics)) > 1:
            route("P1_COMPARE_MIXED_INVALID")
            print("❌ Tidak bisa membandingkan metric yang berbeda dalam satu perintah.")
            print("👉 Contoh yang benar:")
            print("- Bandingkan pengeluaran Januari dan Februari 2025")
            print("- Bandingkan biaya admin Maret dan April 2025")
            print("- Bandingkan pemasukan November dan Desember 2024")
            return

    # ==================================================
    # 5. SIMPLE RULE-BASED QUESTIONS
    # ==================================================
    if not is_analyst_intent and not is_range and "bandingkan" not in q:
        if any(k in q for k in ['admin', 'biaya admin', 'administrasi']):
            route("P2_ADMIN")
            result = get_admin_fees(year, month)
            if result:
                print(f"\n✅ Biaya admin {month}/{year}: Rp {result:,.2f}")
            else:
                print(f"\n⚠️ Tidak ada data biaya admin untuk {month}/{year}")
            return

        if any(k in q for k in ['pemasukan', 'income', 'masuk']):
            route("P3_INCOME")
            result = get_income(year, month)
            if result:
                print(f"\n✅ Pemasukan {month}/{year}: Rp {result:,.2f}")
            else:
                print(f"\n⚠️ Tidak ada data pemasukan untuk {month}/{year}")
            return

        if any(k in q for k in ['pengeluaran', 'expense', 'keluar', 'debit']):
            route("P4_EXPENSE")
            result = get_expenses(year, month)
            if result:
                print(f"\n✅ Pengeluaran {month}/{year}: Rp {result:,.2f}")
            else:
                print(f"\n⚠️ Tidak ada data pengeluaran untuk {month}/{year}")
            return

    # ==================================================
    # 6. TREND / RANGE (NO LLM)
    # ==================================================
    if is_range:
        end_year = year
        if end_month and end_month < month:
            end_year += 1
        
        if end_month:
            trend = get_trend_bulk(year, month, end_year, end_month)
            print(format_trend_report(trend))
        else:
            print("❌ Rentang waktu tidak valid. Pastikan format: 'Jan-Mar 2025' atau 'Januari-Maret 2025'")
        return

    # ==================================================
    # 7. ANALYST MODE (HYBRID LLM + FACTUAL DATA)
    # ==================================================
    if is_analyst_intent:
        route("P6_ANALYST")
        
        # 1. FIRST, GET FACTUAL DATA BASED ON QUESTION
        time_info = extract_year_month(question)
        
        # Define month_map untuk digunakan di bagian ini
        month_map = {
            'januari': 1, 'februari': 2, 'maret': 3, 'april': 4,
            'mei': 5, 'juni': 6, 'juli': 7, 'agustus': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'desember': 12
        }
        
        # Default to available data range if requested date is in future
        if time_info["year"] > data_year or (time_info["year"] == data_year and time_info["month"] > data_month):
            print(f"⚠️  Data hanya tersedia hingga {latest_date[:10]}")
            # Use latest available data instead
            end_year = data_year
            end_month = data_month
            start_month = max(1, end_month - 2)
            start_year = end_year
            if end_month - 2 < 1:
                start_year -= 1
                start_month = 12 + (end_month - 2)
            range_label = f"3 bulan terakhir (data tersedia)"
        else:
            # Use extracted time info
            if time_info.get("is_range", False) and time_info.get("end_month"):
                start_year = time_info["year"]
                start_month = time_info["month"]
                end_year = time_info.get("end_year", start_year)
                end_month = time_info.get("end_month", start_month)
                
                month_names = list(month_map.keys())
                range_label = f"{month_names[start_month-1].capitalize()} - {month_names[end_month-1].capitalize()} {start_year}"
            else:
                # Single month: get 3 months up to that month
                start_month = max(1, time_info["month"] - 2)
                start_year = time_info["year"]
                if time_info["month"] - 2 < 1:
                    start_year -= 1
                    start_month = 12 + (time_info["month"] - 2)
                
                end_year = time_info["year"]
                end_month = time_info["month"]
                range_label = f"3 bulan hingga {time_info['month_name']} {time_info['year']}"
        
        # 2. GET THE ACTUAL DATA
        trend = get_trend_bulk(start_year, start_month, end_year, end_month)
        
        # 3. CHECK IF WE HAVE DATA
        if not trend or not trend.get('months') or len(trend['months']) == 0:
            print(f"❌ Tidak ada data untuk periode {range_label}.")
            
            # Fallback: try to get ANY data to show LLM
            latest_trend = get_trend_bulk(data_year, max(1, data_month-2), data_year, data_month)
            if latest_trend and latest_trend.get('months'):
                print(f"📊 Data terbaru yang tersedia: {len(latest_trend['months'])} bulan")
                data_for_llm = format_trend_report(latest_trend)
            else:
                print("❌ Database kosong atau tidak terbaca.")
                return
        else:
            print(f"📅 Periode analisis: {range_label}")
            print(f"📊 Jumlah bulan data: {len(trend['months'])}")
            
            # 4. SHOW FACTUAL DATA FIRST (ALWAYS)
            print("\n" + "="*60)
            print("📈 DATA FAKTUAL:")
            print("="*60)
            print(format_trend_report(trend))
            
            data_for_llm = format_trend_report(trend)
        
        # 5. Find the specific month if mentioned (SEBELUM LLM)
        target_month = None
        for month_name, month_num in month_map.items():
            if month_name in q:  # Gunakan q yang sudah ada
                target_month = month_num
                break
        
        # 6. NOW USE LLM FOR ANALYSIS (HYBRID APPROACH)
        print("\n" + "="*60)
        print("🤖 ANALISIS AI:")
        print("="*60)
        
        prompt = f"""
    DATA KEUANGAN FAKTUAL:
    {data_for_llm}

    Pertanyaan user: "{question}"

    INSTRUKSI:
    1. Analisis data faktual di atas untuk menjawab pertanyaan
    2. Fokus pada pola yang terlihat dalam data nyata
    3. Jika ada keanehan atau data tidak lengkap, jelaskan
    4. Berikan insight berdasarkan angka-angka yang ada
    5. JANGAN membuat data fiktif atau asumsi tanpa dasar
    6. Gunakan bahasa Indonesia natural

    Analisis:
    """
        
        try:
            # Use LLM for analysis only (no code execution)
            answer = agent.run(
                prompt,
                max_steps=1,
                disable_code_execution=True
            )
            
            print(f"{answer}")
            
            # 7. ADD FACTUAL HIGHLIGHTS AFTER LLM ANALYSIS
            if trend and trend.get('summary'):
                summary = trend['summary']
                print("\n" + "="*60)
                print("🔍 FAKTA PENTING:")
                print("="*60)
                
                # Gunakan target_month yang sudah dicari sebelumnya
                if target_month and 'months' in trend:
                    for month_data in trend['months']:
                        if month_data.get('month') == target_month:
                            print(f"📌 Data spesifik {month_data.get('month_name', '')}:")
                            if 'expense' in month_data:
                                print(f"   • Pengeluaran: Rp {month_data.get('expense', 0):,.2f}")
                            if 'income' in month_data:
                                print(f"   • Pemasukan: Rp {month_data.get('income', 0):,.2f}")
                            if 'admin' in month_data:
                                print(f"   • Biaya admin: Rp {month_data.get('admin', 0):,.2f}")
                            break
                
                # Overall summary
                if 'net_income' in summary:
                    net = summary.get('net_income', 0)
                    status = "Laba" if net >= 0 else "Rugi"
                    print(f"📌 Ringkasan {range_label}:")
                    print(f"   • Status: {status} Rp {abs(net):,.2f}")
                    
        except Exception as e:
            print(f"\n⚠️ Analisis AI gagal: {str(e)}")
            print("💡 Saran: Coba pertanyaan yang lebih spesifik dengan data yang tersedia.")
        
        return

    # ==================================================
    # 8. FALLBACK
    # ==================================================
    print("🤔 Pertanyaan tidak dikenali. Mencoba memahami dengan AI...")
    try:
        # Batasi agent untuk mencegah halusinasi
        answer = agent.run(
            question,
            max_steps=2,
            disable_code_execution=True
        )
        print(f"\n✅ Answer: {answer}")
    except Exception as e:
        print(f"\n❌ Tidak dapat memproses pertanyaan: {str(e)}")
        print("👉 Coba gunakan format yang lebih spesifik, contoh:")
        print("- Berapa pengeluaran Maret 2025?")
        print("- Bandingkan biaya admin April dan Mei 2025")
        print("- Tren pengeluaran Jan-Mar 2025")


# ======================================================
# 7. CLI ENTRY POINT
# ======================================================
if __name__ == "__main__":
    agent = initialize_agent()
    
    earliest, latest = get_data_range()
    if earliest and latest:
        print(f"📊 Data tersedia: {earliest} hingga {latest}")
    
    # Ask if user wants debug mode
    debug_input = input("\n🔧 Enable debug mode? (y/n): ").strip().lower()
    debug_mode = debug_input == 'y' or debug_input == 'yes'
    
    if debug_mode:
        print("🔍 DEBUG MODE ENABLED - Showing detailed information")
    
    while True:
        q = input("\n💬 Tanya keuangan (ketik 'exit' atau 'debug'): ").strip()
        
        if q.lower() == 'exit':
            break
        elif q.lower() == 'debug':
            debug_mode = not debug_mode
            print(f"🔧 Debug mode {'enabled' if debug_mode else 'disabled'}")
            continue
        
        ask(agent, q, debug_mode)
