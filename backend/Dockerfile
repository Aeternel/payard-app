FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gettext \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
ARG INSTALL_DEV=false
RUN pip install --upgrade pip \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install ".[dev]"; else pip install .; fi

COPY . .

RUN useradd --create-home --uid 10001 payyard \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R payyard:payyard /app

USER payyard
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
