# Fly.io / Docker for Text Body Relationship Extractor (FastAPI)
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent data mount point (Fly volume mounts at /data)
RUN mkdir -p /data

EXPOSE 8000

# Use app_fastapi:app and port 8000 for Fly
CMD ["uvicorn", "app_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]
