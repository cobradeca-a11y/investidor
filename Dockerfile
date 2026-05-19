FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FIIA_ENV=prod \
    FIIA_DEBUG=0 \
    FIIA_OBSERVABILIDADE=1 \
    FIIA_DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3)" || exit 1

CMD ["sh", "-c", "python -c \"from config.settings import validar_configuracao_seguranca; import sys; r=validar_configuracao_seguranca(); print('FIIA deploy config:', {k:r[k] for k in ('ambiente','producao','debug','seguro','problemas','avisos')}); sys.exit(0 if r['seguro'] else 1)\" && uvicorn app:app --host 0.0.0.0 --port 8080"]
