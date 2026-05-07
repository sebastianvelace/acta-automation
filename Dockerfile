FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY . .

RUN mkdir -p input output input/processed

EXPOSE 7860

# Hugging Face Spaces usa el puerto 7860 por defecto.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "7860"]
