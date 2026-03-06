# src/ai_agent/cli.py
import json
import re
from router import classify_with_confidence
from metrics import get_income, get_expenses, get_admin_fees
from trend import get_trend_range
from utils import extract_year_month
from agent_layer import build_reasoning_model

# Build LLM reasoning model
reason_model = build_reasoning_model()

def format_trend_data(trend_data: dict):
    """Format trend data into readable summary"""
    lines = []
    lines.append("MONTHLY SUMMARY FROM 'transactions' TABLE")
    lines.append("Source columns: DATE, AMOUNT, MUTATION_TYPE")
    lines.append("")

    months = trend_data["months"]
    
    if not months:
        return "No data available for the specified period."

    for m in months:
        lines.append(f"Month: {m['bulan']}")
        lines.append(f"  Total Income (CR): Rp {m['income']:,.0f}")
        lines.append(f"  Total Expense (DB): Rp {m['expense']:,.0f}")
        lines.append(f"  Net: Rp {m['net']:,.0f}")
        lines.append("")

    # Auto-calculate delta between last two months
    if len(months) >= 2:
        prev = months[-2]
        curr = months[-1]
        
        # Only calculate if both months have data
        if prev['expense'] != 0 or curr['expense'] != 0:
            delta = curr["expense"] - prev["expense"]
            delta_percent = (delta / prev["expense"] * 100) if prev["expense"] != 0 else 0

            lines.append(
                f"Expense change from {prev['bulan']} to {curr['bulan']}: Rp {delta:+,.0f} ({delta_percent:+.1f}%)"
            )
            lines.append("")
    else:
        lines.append("Note: Need at least 2 months of data for trend analysis")
        lines.append("")

    return "\n".join(lines)

def check_data_availability(trend_data: dict, question: str):
    """
    Check if we have enough data to answer the question.
    Returns (has_data, message)
    """
    months = trend_data["months"]
    
    if not months:
        return False, "No data available for the requested period."
    
    # Check if question asks for comparison but only have 1 month
    if "menurun" in question.lower() or "meningkat" in question.lower() or "naik" in question.lower() or "turun" in question.lower():
        if len(months) < 2:
            return False, f"Only have data for {months[0]['bulan']}. Need at least 2 months to analyze increases/decreases."
    
    # Check if specific months have zero data
    for month in months:
        if month['expense'] == 0 and month['income'] == 0:
            print(f"[DEBUG] Warning: {month['bulan']} has zero transactions")
    
    return True, ""

def run_agent_structured(model, question: str, context_data: dict, data_status: str = ""):
    """
    Run structured reasoning with LLM.
    Includes data context to help model understand limitations.
    """
    formatted_data = format_trend_data(context_data)
    
    # Add context about data availability
    data_context = f"""
DATA AVAILABILITY NOTE: {data_status}

{formatted_data}
"""
    
    # Even simpler prompt for 3B model
    structured_prompt = f"""Anda adalah analis keuangan profesional. 
Gunakan data berikut untuk menjawab:
{data_context}

Beberapa transaksi penting di periode ini:
    - TARIKAN ATM
    - TRSF E-BANKING (Transfer)
    - BIAYA ADM
    - TOPUP FLAZZ

Pertanyaan: {question}

Aturan Ketat:
1. Jawab dalam satu kalimat Bahasa Indonesia yang jelas.
2. Sebutkan angka rupiahnya jika ada.
3. Jawab HANYA dalam format JSON: {{"answer": "isi jawaban", "confidence": 0.9}}
4. Jika data tidak cukup, katakan data tidak tersedia.

Tugas: Jawab pertanyaan berdasarkan DATA SAJA. 
- Jika pengeluaran turun, sebutkan selisih angkanya.
- JANGAN membuat alasan seperti 'beasiswa' atau 'modal' jika tidak ada di data.
- Jika tidak tahu alasannya, katakan: "Pengeluaran turun dari Rp X ke Rp Y, namun alasan spesifik tidak tercatat di deskripsi transaksi."
"""
    
    response = model.generate(
        messages=[
            {"role": "user", "content": structured_prompt}
        ]
    )
    
    return response.content

def clean_json_response(response: str):
    """
    Aggressively clean and extract JSON from model response.
    """
    response = response.strip()
    
    # Remove markdown code blocks
    response = re.sub(r'```json\s*', '', response)
    response = re.sub(r'```\s*', '', response)
    
    # Try to find JSON pattern
    json_pattern = r'\{[^{}]*\}'
    matches = re.findall(json_pattern, response)
    
    if matches:
        # Take the longest match
        return max(matches, key=len)
    
    # If no JSON found, create minimal valid JSON
    return '{"answer": "Unable to generate analysis", "confidence": 0.0}'

def validate_json_output(response: str):
    """
    Validate and parse JSON response.
    """
    try:
        parsed = json.loads(response)
        
        # Ensure required fields
        if "answer" not in parsed:
            parsed["answer"] = "Analysis unavailable"
        
        if "confidence" not in parsed:
            parsed["confidence"] = 0.3
        
        return True, parsed
        
    except json.JSONDecodeError:
        # Create default response
        return True, {
            "answer": "Could not analyze the data properly",
            "confidence": 0.1
        }

def hallucination_guard(answer_text: str):
    """
    Check for uncertain or speculative language.
    """
    suspicious_words = [
        "mungkin", "sepertinya", "diperkirakan", "barangkali",
        "maybe", "perhaps", "probably", "possibly", "might",
        "could be", "i think", "i believe", "my analysis"
    ]
    
    answer_lower = answer_text.lower()
    for word in suspicious_words:
        if word in answer_lower:
            return True
    
    return False

def generate_simple_analysis(trend_data: dict, question: str):
    """
    Generate simple analysis based on available data without LLM.
    """
    months = trend_data["months"]
    
    if len(months) == 0:
        return "No data available for analysis."
    
    if len(months) == 1:
        month = months[0]
        return f"Data only available for {month['bulan']} with expense Rp {month['expense']:,.0f}. Cannot analyze trends."
    
    # We have at least 2 months
    prev = months[-2]
    curr = months[-1]
    
    # Check if either month has zero data
    if prev['expense'] == 0 and curr['expense'] == 0:
        return f"Both {prev['bulan']} and {curr['bulan']} have no expense data."
    elif prev['expense'] == 0:
        return f"{prev['bulan']} has no expense data, cannot calculate change to {curr['bulan']}."
    elif curr['expense'] == 0:
        return f"{curr['bulan']} has no expense data, cannot calculate change from {prev['bulan']}."
    
    # Calculate changes
    delta = curr["expense"] - prev["expense"]
    delta_percent = (delta / prev["expense"] * 100)
    
    # Check if question is about decrease
    is_decrease_question = any(word in question.lower() for word in ["menurun", "turun", "decrease", "drop"])
    is_increase_question = any(word in question.lower() for word in ["meningkat", "naik", "increase", "rise"])
    
    if is_decrease_question and delta > 0:
        return f"Expense actually increased by Rp {delta:,.0f} ({delta_percent:+.1f}%) from {prev['bulan']} to {curr['bulan']}, not decreased."
    elif is_increase_question and delta < 0:
        return f"Expense actually decreased by Rp {abs(delta):,.0f} ({delta_percent:+.1f}%) from {prev['bulan']} to {curr['bulan']}, not increased."
    elif delta < 0:
        return f"Expense decreased by Rp {abs(delta):,.0f} ({abs(delta_percent):.1f}%) from {prev['bulan']} to {curr['bulan']}."
    elif delta > 0:
        return f"Expense increased by Rp {delta:,.0f} ({delta_percent:+.1f}%) from {prev['bulan']} to {curr['bulan']}."
    else:
        return f"Expense remained stable at Rp {curr['expense']:,.0f} from {prev['bulan']} to {curr['bulan']}."

def handle_question(question: str):
    """Main handler for all questions"""
    
    # Classify intent
    intent, confidence = classify_with_confidence(question)
    print(f"[DEBUG] Intent: {intent}, Confidence: {confidence}")
    
    # Extract time information
    time_info = extract_year_month(question)
    year = time_info["year"]
    month = time_info["month"]
    
    # =============================
    # 1️⃣ DETERMINISTIC LAYER
    # =============================
    
    if intent == "income":
        amount = get_income(year, month)
        return f"Income for {month}/{year}: Rp {amount:,.2f}"
    
    if intent == "expense":
        amount = get_expenses(year, month)
        return f"Expense for {month}/{year}: Rp {amount:,.2f}"
    
    if intent == "admin":
        amount = get_admin_fees(year, month)
        return f"Admin fees for {month}/{year}: Rp {amount:,.2f}"
    
    if intent == "trend":
        # Take advantage of extracted time range for trend
        trend_data = get_trend_range(
            time_info["year"], 
            time_info["month"], 
            time_info.get("end_year", time_info["year"]), 
            time_info.get("end_month", time_info["month"])
        )
        return format_trend_data(trend_data)
        return format_trend_data(trend_data)
    
    # =============================
    # 2️⃣ ANALYSIS LAYER
    # =============================
    
    if intent == "analysis":
        # Get data for requested period
        end_year = time_info.get("end_year", year)
        end_month = time_info.get("end_month", month)
        
        trend_data = get_trend_range(year, month, end_year, end_month)
        
        # Check data availability first
        has_data, data_message = check_data_availability(trend_data, question)
        if not has_data:
            return data_message
        
        # For simple analysis with limited data, use fallback directly
        months = trend_data["months"]
        if len(months) < 2 or any(m['expense'] == 0 for m in months[-2:]):
            print("[DEBUG] Using fallback analysis (insufficient or zero data)")
            return generate_simple_analysis(trend_data, question)
        
        # Try LLM for more complex analysis
        print("[DEBUG] Reasoning model triggered")
        
        # Single attempt with better context
        response = run_agent_structured(
            reason_model,
            question,
            trend_data,
            data_message
        )
        
        print("[DEBUG] Raw Model Output:", response[:200])
        
        cleaned_response = clean_json_response(response)
        valid, result = validate_json_output(cleaned_response)
        
        if valid and result["confidence"] >= 0.3 and not hallucination_guard(result["answer"]):
            return result["answer"]
        
        # Fallback to simple analysis
        print("[DEBUG] Using fallback analysis")
        return generate_simple_analysis(trend_data, question)
    
    return "Question not recognized. Please ask about income, expenses, admin fees, trends, or analysis."

def test_mode():
    """Test function to verify all components work"""
    test_questions = [
        "berapa pengeluaran november 2024?",
        "kenapa pengeluaran november-desember 2024 menurun?",
        "analisis trend expense akhir tahun 2024",
        "income desember 2024",
        "trend bulan november 2024",
        "trend november 2024 sampai januari 2025"
    ]
    
    print("=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)
    
    for q in test_questions:
        print(f"\n❓ Q: {q}")
        result = handle_question(q)
        print(f"💡 A: {result}")
        print("-" * 40)
    
    print("\n✅ Tests completed")

# =========================
# CLI ENTRY POINT
# =========================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_mode()
        sys.exit(0)
    
    print("🤖 Hybrid Financial AI (Stable Mode)")
    print("Type 'exit' to quit, 'test' for test mode\n")
    
    while True:
        q = input("💬 Tanya: ").strip()
        
        if q.lower() == "exit":
            print("👋 Goodbye!")
            break
        
        if q.lower() == "test":
            test_mode()
            continue
        
        if not q:
            continue
        
        output = handle_question(q)
        
        print("\n📊 RESULT:")
        print(output)
        print("-" * 60)