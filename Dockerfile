# Use Python 3.12-slim as base image
FROM python:3.12-slim

# 1. Install dependencies sistem & locale Indonesia
RUN apt-get update && apt-get install -y \
    sqlite3 \
    locales \
    tzdata \
    && sed -i -e 's/# id_ID.UTF-8 UTF-8/id_ID.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# 2. Set Environment Variables for locale Indonesia & timezone Jakarta
ENV LANG=id_ID.UTF-8
ENV LANGUAGE=id_ID:id
ENV LC_ALL=id_ID.UTF-8
ENV TZ=Asia/Jakarta

# Set working directory
WORKDIR /app

# 3. Copy requirements.txt (Optimasi Cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy all project files
COPY . .

# Make sure necessary directories exist
RUN mkdir -p logs data/database

ENV PYTHONPATH="/app:/app/src:/app/src/ai_agent:/app/src/data_pipeline"

# Default command
CMD ["python", "src/ai_agent/llm_agent.py"]