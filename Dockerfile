# Indian Day Trader API + bundled web app. Read-only market data; never places orders.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IDT_HOME=/data \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[server]" \
 && useradd --system --uid 10001 idt \
 && mkdir -p /data && chown idt /data

USER idt
VOLUME /data
EXPOSE 8742
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8742/api/health', timeout=4)"

CMD ["idt", "serve", "--host", "0.0.0.0", "--port", "8742"]
