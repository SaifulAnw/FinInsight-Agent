def classify_intent(question: str) -> str:
    """
    Classify user intent deterministically.
    No LLM used here.
    """

    q = question.lower()

    if "bandingkan" in q:
        return "compare"

    if any(k in q for k in ["tren", "trend"]):
        return "trend"

    if any(k in q for k in ["analisa", "analisis", "kenapa", "insight", "evaluasi"]):
        return "analysis"

    if any(k in q for k in ["admin", "biaya admin", "administrasi"]):
        return "admin"

    if any(k in q for k in ["pemasukan", "income", "masuk"]):
        return "income"

    if any(k in q for k in ["pengeluaran", "expense", "keluar", "debit"]):
        return "expense"

    return "unknown"

def classify_with_confidence(question: str):
    intent = classify_intent(question)

    # Basic confidence heuristic
    if intent != "unknown":
        return intent, 0.9

    if len(question.split()) < 3:
        return "unknown", 0.2

    return "analysis", 0.5