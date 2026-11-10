FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 tesseract-ocr-eng tesseract-ocr-rus tesseract-ocr-kaz && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir -r requirements.txt gunicorn && python -m playwright install --with-deps chromium
COPY . .
CMD gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 180 app:app
