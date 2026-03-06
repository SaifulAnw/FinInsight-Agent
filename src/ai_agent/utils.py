import locale
from datetime import datetime
import re

# Set locale for Indonesian currency format
try:
    locale.setlocale(locale.LC_ALL, 'id_ID.UTF-8')
except:
    locale.setlocale(locale.LC_ALL, '')  # Fallback if ID locale is unavailable

def format_currency(value):
    """Converts number to IDR format (e.g., Rp 1,000,000)"""
    if value is None: return "Rp 0"
    return locale.currency(value, grouping=True, symbol=True)

def shift_month(year, month, delta):
    """Calculates previous or next month (e.g., 1 month before Jan 2024 is Dec 2023)"""
    new_month = (month - 1 + delta) % 12 + 1
    new_year = year + (month - 1 + delta) // 12
    return int(new_year), int(new_month)

def get_month_name(month_number):
    """Converts month number to English month name"""
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    return months[month_number - 1]

def extract_year_month(question: str):
    question_lower = question.lower()
    
    # Search for all years in the question
    years = [int(y) for y in re.findall(r'(20\d{2})', question_lower)]
    
    month_map = {'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6, 
                 'juli': 7, 'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12}
    
    found_months = []
    for name, num in month_map.items():
        if name in question_lower:
            # Search for the position of the month name in the question to maintain order
            found_months.append((question_lower.find(name), num))
    
    found_months.sort() 
    months = [m[1] for m in found_months]
    
    if "akhir tahun" in question_lower and not months:
        months = [10, 11, 12]
    if "awal tahun" in question_lower and not months:
        months = [1, 2, 3]

    start_year = years[0] if len(years) > 0 else datetime.now().year
    end_year = years[1] if len(years) > 1 else (years[0] if len(years) > 0 else start_year)
    
    start_month = months[0] if len(months) > 0 else datetime.now().month
    end_month = months[-1] if len(months) > 0 else start_month

    return {
        "year": start_year,
        "month": start_month,
        "end_year": end_year,
        "end_month": end_month
    }

def format_trend_report(trend_data):
    """Creates a simple text table for trend report based on SQL Tuples"""
    if not trend_data:
        return "No data for the selected period."
    
    report = "📊 **Financial Trend Report:**\n"
    # Header Tabel
    report += f"{'Periode':<10} | {'Pemasukan':<15} | {'Pengeluaran':<15} | {'Balance':<15}\n"
    report += "-" * 65 + "\n"

    all_income_zero = True 
    
    for row in trend_data:
        # row[0] = 'YYYY-MM'
        # row[1] = pemasukan
        # row[2] = pengeluaran
        periode = row[0]
        pemasukan = row[1] if row[1] else 0
        pengeluaran = row[2] if row[2] else 0
        
        if pemasukan > 0:
            all_income_zero = False
        
        balance = pemasukan - pengeluaran
        report += (
            f"{periode:<10} | "
            f"{format_currency(pemasukan):<15} | "
            f"{format_currency(pengeluaran):<15} | "
            f"{format_currency(balance):<15}\n"
        )
    
    # ⚠️ WARNING KHUSUS (SETELAH LOOP)
    if all_income_zero:
        report += (
            "\n⚠️ Tidak ditemukan transaksi pemasukan pada periode ini.\n"
            "ℹ️ Pastikan pemasukan memang tercatat sebagai MUTATION_TYPE = 'CR'."
        )

    return report
# ======================================================