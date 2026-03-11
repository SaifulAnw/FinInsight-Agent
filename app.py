import streamlit as st
import pandas as pd
from src.ai_agent.cli import handle_question
from src.ai_agent.metrics import (
    get_tracked_period,
    get_trend_dataframe,
    get_latest_transactions
)

start, end = get_tracked_period()
start_fmt = pd.to_datetime(start).strftime("%b %Y")
end_fmt = pd.to_datetime(end).strftime("%b %Y")

# ---------------------------------------------------
# Page Configuration
# ---------------------------------------------------

st.set_page_config(
    page_title="FinInsight AI Dashboard",
    page_icon="💰",
    layout="wide"
)

# ---------------------------------------------------
# Header Section
# ---------------------------------------------------

st.title("💰 FinInsight-Agent")
st.subheader("Hybrid SQL + LLM Financial Analyst")

st.markdown(
"""
This system uses a **Hybrid SQL–LLM architecture**:

- **SQL Layer** → performs deterministic financial calculations  
- **LLM Layer** → generates natural language financial insights  

This design reduces hallucination while keeping explanations intuitive.
"""
)

st.divider()

# ---------------------------------------------------
# Sidebar: System Information
# ---------------------------------------------------

with st.sidebar:

    st.header("⚙️ System Status")

    st.success("Database: SQLite Connected")
    st.info("Logic Layer: Deterministic SQL")
    st.info("LLM Model: Qwen2.5-Coder (Ollama)")
    st.info("Architecture: Hybrid SQL + LLM")

    st.divider()

    st.header("📊 Example Queries")

    st.markdown(
    """
    - Berapa pengeluaran saya pada Januari 2025?
    - Kenapa pengeluaran November - Desember 2024 menurun?
    - Tunjukkan tren keuangan dari November 2024 sampai Januari 2025
    """
    )

# ---------------------------------------------------
# Optional Summary Metrics
# (placeholder for future DB summary queries)
# ---------------------------------------------------

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
    label="Tracked Period",
    value=f"{start_fmt} – {end_fmt}"
)

with col2:
    st.metric(label="Analysis Engine", value="Hybrid AI")

with col3:
    st.metric(label="Mode", value="Stable")

# ---------------------------------------------------
# Query Interface
# ---------------------------------------------------

st.subheader("💬 Tanya FinInsight")

query = st.text_input(
    "Tanyakan sesuatu tentang keuanganmu:",
    placeholder="Contoh: Kenapa pengeluaran November ke Desember 2024 turun?"
)

# ---------------------------------------------------
# Query Execution
# ---------------------------------------------------

if query:

    with st.spinner("AI Agent is analyzing financial data..."):

        try:
            # Call the main orchestration function
            response_text = handle_question(query)

            st.subheader("Response Agent")

            # If response is a text table (trend summary)
            if "MONTHLY SUMMARY" in response_text:

                lines = response_text.split("\n")

                rows = []
                month = income = expense = net = None

                for line in lines:

                    line = line.strip()

                    if line.startswith("Month:"):
                        month = line.split(":")[1].strip()

                    elif "Total Income" in line:
                        income = int(line.split("Rp")[1].replace(",", ""))

                    elif "Total Expense" in line:
                        expense = int(line.split("Rp")[1].replace(",", ""))

                    elif line.startswith("Net"):
                        net = int(line.split("Rp")[1].replace(",", ""))

                        rows.append({
                            "Month": month,
                            "Income": income,
                            "Expense": expense,
                            "Net": net
                        })

                df = pd.DataFrame(rows)

                st.subheader("📊 Financial Trend")

                df_display = df.copy()
                df_display["Income"] = df_display["Income"].apply(lambda x: f"Rp {x:,.0f}")
                df_display["Expense"] = df_display["Expense"].apply(lambda x: f"Rp {x:,.0f}")
                df_display["Net"] = df_display["Net"].apply(lambda x: f"Rp {x:,.0f}")

                st.dataframe(df_display)
                df = df.sort_values("Month")

                st.line_chart(
                    df.set_index("Month")[["Income", "Expense"]]
                )
                
                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "Total Income",
                    f"Rp {df['Income'].sum():,.0f}"
                )

                col2.metric(
                    "Total Expense",
                    f"Rp {df['Expense'].sum():,.0f}"
                )

                col3.metric(
                    "Net Balance",
                    f"Rp {df['Net'].sum():,.0f}"
                )

            else:
                st.success(response_text)

        except Exception as e:
            st.error(f"⚠ Error processing query: {e}")

st.divider()

# ---------------------------------------------------
# Latest Transactions
# ---------------------------------------------------

st.subheader("📑 Latest Transactions")

transactions_df = get_latest_transactions()

st.dataframe(transactions_df)

# ---------------------------------------------------
# Expense Trend Visualization
# ---------------------------------------------------

st.subheader("📊 Expense Trend")

trend_df = get_trend_dataframe()

st.line_chart(
    trend_df.set_index("month")["expense"]
)

# ---------------------------------------------------
# Footer
# ---------------------------------------------------

st.divider()

st.caption(
"""
Built by **Saiful Anwar**  
Hybrid AI Financial Analysis System | Portfolio Project
"""
)