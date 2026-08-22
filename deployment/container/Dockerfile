ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIELDORA_DATA_ROOT=/var/lib/fieldora

RUN groupadd --system --gid 10001 fieldora \
    && useradd --system --uid 10001 --gid fieldora --home /nonexistent fieldora \
    && mkdir -p /var/lib/fieldora \
    && chown fieldora:fieldora /var/lib/fieldora
WORKDIR /opt/fieldora
COPY . /opt/fieldora
RUN pip install --no-cache-dir ".[server-postgresql,server-s3]"

USER 10001:10001
EXPOSE 8765
ENTRYPOINT ["fieldora-server"]
