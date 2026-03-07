FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY tests/ tests/
COPY seed_fake_data.py .

# No pre-seeded DB — app will snapshot from iNat on startup

# Render sets PORT env var (default 10000)
ENV PORT=10000

EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
