FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY frontend /app/frontend
COPY .env.example /app/.env.example

EXPOSE 8000 25

CMD ["python", "-m", "app.main"]
