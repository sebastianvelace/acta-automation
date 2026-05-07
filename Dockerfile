FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway (y otros hosts) suelen definir PORT; localmente cae en 8000.
CMD ["sh", "-c", "exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
