def analyze_trend(agent, trend_data: dict, question: str):
    """
    Use LLM only for insight generation.
    No SQL, no calculations here.
    """

    if not trend_data or not trend_data.get("months"):
        return "Tidak ada data untuk dianalisis."

    prompt = f"""
DATA KEUANGAN FAKTUAL:
{trend_data}

Pertanyaan user:
{question}

ATURAN KERAS:
1. Jangan membuat angka baru
2. Jangan mengarang data
3. Hanya gunakan angka dalam DATA KEUANGAN FAKTUAL
4. Jika data kurang, katakan tidak cukup

Berikan analisis profesional dalam Bahasa Indonesia.
"""

    try:
        result = agent.run(
            prompt,
            max_steps=1,
            disable_code_execution=True
        )
        return result

    except Exception as e:
        return f"Analisis AI gagal: {str(e)}"