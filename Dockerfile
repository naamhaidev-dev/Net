FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install requirements.txt
COPY . .
CMD ["python", "netflix_bot.py"]
