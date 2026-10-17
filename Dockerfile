FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt -r requirements.txt \
    && useradd --create-home --uid 10001 pelifolk
COPY --chown=pelifolk:pelifolk main.py ./
COPY --chown=pelifolk:pelifolk src ./src
COPY --chown=pelifolk:pelifolk database ./database
COPY --chown=pelifolk:pelifolk scripts ./scripts
RUN mkdir -p /app/upload/photos_profile && chown -R pelifolk:pelifolk /app/upload
USER pelifolk
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
