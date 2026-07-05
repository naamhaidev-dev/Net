FROM python:3.10-slim

WORKDIR /app

# ✅ SAHI COMMAND - -r flag use karo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY netflix_bot.py .

CMD ["python", "netflix_bot.py"]
