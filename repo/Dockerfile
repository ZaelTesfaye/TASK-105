FROM python:3.12-slim

WORKDIR /app

# System deps for bcrypt / eventlet
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data dirs are volume-mounted; create placeholders so the image works standalone
RUN mkdir -p data/attachments data/keys data/logs

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
ENV FLASK_APP=app:create_app

EXPOSE 5000

ENTRYPOINT ["bash", "scripts/start.sh"]
