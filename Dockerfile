# Indian Day Trader API + bundled web app. Read-only market data; never places orders.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IDT_HOME=/data \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first (own cached layer): code changes don't reinstall pandas/matplotlib.
COPY pyproject.toml README.md ./
RUN mkdir -p src/idt && touch src/idt/__init__.py \
 && pip install --no-cache-dir ".[server]" \
 && pip uninstall -y indian-day-trader

COPY src ./src
# The first install left build/ with the stub __init__.py; setuptools would reuse it. Clear it.
RUN rm -rf build src/*.egg-info \
 && pip install --no-cache-dir --no-deps . \
 && useradd --system --uid 10001 idt \
 && mkdir -p /data && chown idt /data

USER idt
VOLUME /data
EXPOSE 8742
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8742/api/health', timeout=4)"

CMD ["idt", "serve", "--host", "0.0.0.0", "--port", "8742"]
