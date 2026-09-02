FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запускаем напрямую Python-скрипт, чтобы увидеть ошибки
CMD ["python", "main.py"]
