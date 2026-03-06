# test_database.py
import os
import sys
sys.path.append('.')

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def test_queries():
    print("🔍 TESTING DATABASE CONNECTION")
    print(f"Database: {DATABASE_URL}")
    print("="*60)
    
    queries = [
        {
            "name": "Admin Transactions",
            "sql": """
            SELECT COUNT(*) as count, SUM(AMOUNT) as total 
            FROM transactions 
            WHERE DESCRIPTION LIKE '%ADMIN%' OR DESCRIPTION LIKE '%BIAYA ADM%'
            """
        },
        {
            "name": "November 2024 Data",
            "sql": """
            SELECT DATE, DESCRIPTION, AMOUNT, MUTATION_TYPE
            FROM transactions 
            WHERE DATE LIKE '2024-11%'
            ORDER BY DATE DESC
            LIMIT 10
            """
        },
        {
            "name": "Transaction Types",
            "sql": """
            SELECT 
                COUNT(*) as total_transactions,
                COUNT(CASE WHEN DESCRIPTION LIKE '%ADMIN%' OR DESCRIPTION LIKE '%BIAYA ADM%' THEN 1 END) as admin_count,
                COUNT(CASE WHEN DESCRIPTION LIKE 'KR OTOMATIS%' OR DESCRIPTION LIKE 'SETORAN%' OR DESCRIPTION LIKE 'BI-FAST%' THEN 1 END) as income_count,
                COUNT(CASE WHEN MUTATION_TYPE = 'DB' OR DESCRIPTION LIKE '%DEBIT%' OR DESCRIPTION LIKE '%TRSF E-BANKING%' THEN 1 END) as expense_count
            FROM transactions
            """
        },
        {
            "name": "Sample Admin Transactions",
            "sql": """
            SELECT DATE, DESCRIPTION, AMOUNT
            FROM transactions
            WHERE DESCRIPTION LIKE '%ADMIN%' OR DESCRIPTION LIKE '%BIAYA ADM%'
            ORDER BY DATE DESC
            LIMIT 5
            """
        }
    ]
    
    with engine.connect() as conn:
        for query_info in queries:
            print(f"\n📊 {query_info['name']}")
            print("-" * 40)
            
            try:
                result = conn.execute(text(query_info["sql"]))
                columns = result.keys()
                
                # Print header
                print(" | ".join(columns))
                print("-" * 40)
                
                # Print data
                rows = result.fetchall()
                if not rows:
                    print("No data found")
                else:
                    for row in rows:
                        print(" | ".join(str(value) if value is not None else "NULL" for value in row))
                        
            except Exception as e:
                print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_queries()