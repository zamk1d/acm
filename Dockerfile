FROM python:3.13-slim

# ffmpeg + ffprobe as static binaries — multi-arch, works on amd64 and arm64 hosts.
# Must be before any regular COPY (Docker requires all COPY --from first).
COPY --from=mwader/static-ffmpeg:7.1 /ffmpeg /usr/local/bin/ffmpeg
COPY --from=mwader/static-ffmpeg:7.1 /ffprobe /usr/local/bin/ffprobe
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src

WORKDIR /app

# dependencies first (cached layer); uv.lock is used if present
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "acm.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]