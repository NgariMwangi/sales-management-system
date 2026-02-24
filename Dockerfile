# Sales Management System - Docker image
FROM python:3.12-slim

# Create app user and directory
RUN useradd -m -u 1000 appuser
WORKDIR /app

# Install system deps for psycopg2 and reportlab
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY --chown=appuser:appuser . .

# Non-root user
USER appuser

ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1
EXPOSE 5000

# Default: run with gunicorn (override in docker-compose for flask run if needed)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "wsgi:app"]
