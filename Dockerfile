FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HOME=/home/appuser \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser anon/ anon/
COPY --chown=appuser:appuser frontend/ frontend/
COPY --chown=appuser:appuser app.py .

USER appuser

# Модели Natasha качаются при первом вызове; кладём их в образ заранее.
RUN python -c "from natasha import NewsEmbedding, NewsMorphTagger, NewsNERTagger; e = NewsEmbedding(); NewsMorphTagger(e); NewsNERTagger(e)"

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"

# Флаги перекрывают локальный .streamlit/config.toml (там address=127.0.0.1).
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.maxUploadSize=500", \
     "--server.fileWatcherType=none", \
     "--browser.serverAddress=localhost", \
     "--browser.gatherUsageStats=false"]
