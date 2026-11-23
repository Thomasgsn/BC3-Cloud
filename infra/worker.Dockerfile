FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS dependencies
COPY requirements.worker.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --target=/install --only-binary=:all: --require-hashes -r /tmp/requirements.lock
FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
RUN apt-get update && apt-get install -y --only-upgrade zlib1g && rm -rf /var/lib/apt/lists/*
RUN python -m pip uninstall -y pip
WORKDIR /app
COPY --from=dependencies /install /usr/local/lib/python3.12/site-packages
COPY src/rncp_bc3/__init__.py src/rncp_bc3/config.py src/rncp_bc3/db.py src/rncp_bc3/security.py src/rncp_bc3/storage.py src/rncp_bc3/worker.py /app/src/rncp_bc3/
RUN useradd --uid 10001 --create-home bc3
USER 10001
CMD ["python","-m","rncp_bc3.worker"]
