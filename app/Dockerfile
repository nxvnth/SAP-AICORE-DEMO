FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching — only rebuilds if requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code — .dockerignore ensures .env is never copied
COPY main.py .
COPY ingest.py .
COPY auth.py .

# The app listens on 8080 (required by KServe / SAP AI Core)
EXPOSE 8080

# Default: run the chatbot server
# Override with ["python", "ingest.py"] in the workflow template
CMD ["python", "main.py", "--mode", "serve"]
