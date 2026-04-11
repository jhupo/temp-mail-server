FROM node:22-bookworm AS frontend-builder

WORKDIR /app/mail-vue
COPY mail-vue /app/mail-vue
RUN npm install --legacy-peer-deps
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY --from=frontend-builder /app/mail-vue/dist /app/mail-vue/dist

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
