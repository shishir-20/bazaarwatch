FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8000
# Render/other clouds set $PORT; default to 8000 locally
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8000} app:app"]