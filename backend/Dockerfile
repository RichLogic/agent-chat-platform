FROM python:3.11-slim

WORKDIR /app

# System deps for lxml, pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Default: run the backend API
CMD ["uvicorn", "agent_chat.main:app", "--host", "0.0.0.0", "--port", "8301"]
