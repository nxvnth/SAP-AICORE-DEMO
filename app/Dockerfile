FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching — only rebuilds if requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake HuggingFace Embeddings directly into Docker Image Cache to eliminate cold start internet dependencies
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
# Copy application code — .dockerignore ensures .env is never copied
COPY main.py .
COPY ingest.py .
COPY auth.py .

# The app listens on 8080 (required by KServe / SAP AI Core)
EXPOSE 8080

# Default: run the chatbot server
# Override with ["python", "ingest.py"] in the workflow template
CMD ["python", "main.py", "--mode", "serve"]
