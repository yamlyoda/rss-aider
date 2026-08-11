# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY pyproject.toml .

# Install Python dependencies using uv
RUN pip install uv
RUN uv pip install --system --no-cache-dir -e .

# Download SpaCy model
RUN python -c "import spacy; spacy.cli.download('ru_core_news_sm')"

# Copy application code
COPY . .

# Expose ports for monitor and worker
EXPOSE 8000 8001

# Default command (can be overridden)
CMD ["python", "monitor.py"]
````
