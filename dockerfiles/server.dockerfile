# Base image
FROM python:3.11-slim

ENV HOST 0.0.0.0
ENV PORT 8080

EXPOSE 8080

RUN apt update && \
    apt install --no-install-recommends -y build-essential gcc && \
    apt clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
COPY requirements_dev.txt requirements_dev.txt
COPY pyproject.toml pyproject.toml
COPY src/ src/
COPY data/testing data/testing
COPY models/model0 models/model0

WORKDIR /
RUN pip install -r requirements.txt
RUN pip install -r requirements_dev.txt
RUN pip install . --no-deps --no-cache-dir
RUN gsutil cp gs://project-mloperations-data/data/drifting/current_data.csv data/drifting/current_data.csv

ENTRYPOINT exec uvicorn src.server.main:app --port 8080 --host 0.0.0.0
