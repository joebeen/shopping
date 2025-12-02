FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Nur die wirklich benötigten Pakete
RUN pip install --no-cache-dir flask flask_sqlalchemy sqlalchemy
RUN mkdir -p /data

# App-Code kopieren
COPY app.py /app/
COPY templates /app/templates

# SQLite-Datei liegt in /data (wird in OpenShift als Volume gemountet)
ENV DB_PATH=/data/shopping.db


EXPOSE 8080

# Kein Gunicorn – direkt Flask starten
CMD ["python", "app.py"]