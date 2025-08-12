FROM python:3.11-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src

# Render는 컨테이너가 $PORT로 리스닝해야 함
EXPOSE 8000
CMD ["sh","-c","uvicorn src.app:app --host 0.0.0.0 --port ${PORT:-8000}"]