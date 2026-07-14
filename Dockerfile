# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md requirements.runtime.lock ./
COPY backend ./backend
RUN python -m pip install --upgrade pip build wheel "setuptools>=80" \
    && python -m build --wheel --no-isolation

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    CEO_VOICE_APPLICATION__ENVIRONMENT=production \
    CEO_VOICE_APPLICATION__DEBUG=false \
    CEO_VOICE_LOGGING__FORMAT=json \
    CEO_VOICE_LOGGING__LEVEL=INFO

RUN groupadd --system --gid 10001 ceovoice \
    && useradd --system --uid 10001 --gid ceovoice --create-home ceovoice
WORKDIR /app
COPY requirements.runtime.lock ./
COPY --from=build /build/dist/*.whl /tmp/package/
RUN python -m pip install -r requirements.runtime.lock /tmp/package/*.whl \
    && rm -rf /tmp/package
RUN mkdir -p /app/workspace /app/exports && chown -R ceovoice:ceovoice /app

USER ceovoice
VOLUME ["/app/workspace", "/app/exports"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["ceo-voice", "doctor"]
ENTRYPOINT ["ceo-voice"]
CMD ["doctor"]
