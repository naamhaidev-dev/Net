FROM python:3.10-slim

WORKDIR /app

# Copy requirements first
COPY requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy application
COPY netflix_bot.py /app/netflix_bot.py

# Command
CMD ["python", "/app/netflix_bot.py"]
