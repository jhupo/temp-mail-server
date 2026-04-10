FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json /frontend/package.json
RUN npm install --legacy-peer-deps

COPY frontend /frontend
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY --from=frontend-builder /frontend/dist /app/frontend/dist
COPY .env.example /app/.env.example

EXPOSE 8000 25

CMD ["python", "-m", "app.main"]
