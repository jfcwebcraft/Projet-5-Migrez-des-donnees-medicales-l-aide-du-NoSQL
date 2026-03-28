FROM python:3.11-slim

RUN pip install --no-cache-dir pandas pymongo python-dotenv

WORKDIR /app
COPY loader.py /app/loader.py

ENV PYTHONUNBUFFERED=1
