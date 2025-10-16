# Development Dockerfile for Flask API
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv venv

# Copy requirements and install Python dependencies in venv
COPY requirements.txt .
RUN venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for models and other data
RUN mkdir -p models data utils actions

# Set environment variables for development
ENV PYTHONPATH=/app
ENV FLASK_APP=app.py
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1

# Expose port
EXPOSE 5000

# Run the application using venv
CMD ["venv/bin/python", "app.py"]
