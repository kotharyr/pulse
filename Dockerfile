FROM python:3.12-slim
WORKDIR /app
<<<<<<< HEAD
COPY pyproject.toml README.md ./
COPY src src
RUN pip install --no-cache-dir .
COPY config config
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3)"]
=======
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
COPY config config
ENV PYTHONPATH=/app/src
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
CMD ["python","-m","engineering_ops.server"]
