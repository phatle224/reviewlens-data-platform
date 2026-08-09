# syntax=docker/dockerfile:1.18
FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv
FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS runtime

ENV PATH="/opt/reviewlens/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --gid 10001 reviewlens \
    && useradd --uid 10001 --gid reviewlens --create-home --shell /usr/sbin/nologin reviewlens \
    && mkdir -p /opt/reviewlens \
    && chown reviewlens:reviewlens /opt/reviewlens

COPY --from=uv /uv /uvx /bin/
WORKDIR /opt/reviewlens
COPY --chown=reviewlens:reviewlens pyproject.toml uv.lock README.md ./
COPY --chown=reviewlens:reviewlens src ./src
COPY --chown=reviewlens:reviewlens config ./config

USER 10001:10001
RUN uv sync --locked --no-dev --extra app --no-editable --no-cache

EXPOSE 8501 9108
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)" || exit 1

ENTRYPOINT ["reviewlens-app"]

