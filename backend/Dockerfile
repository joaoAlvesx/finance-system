FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system finance && useradd --system --gid finance --home-dir /app finance

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

COPY alembic.ini ./
COPY alembic ./alembic

USER finance

FROM base AS runtime

EXPOSE 8000

CMD ["sh", "-c", "python -m app.db.wait_for_database && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM base AS worker

CMD ["sh", "-c", "python -m app.db.wait_for_database && python -m app.worker"]

FROM base AS test

USER root
RUN pip install ".[dev]"
COPY tests ./tests
USER finance

CMD ["pytest"]
