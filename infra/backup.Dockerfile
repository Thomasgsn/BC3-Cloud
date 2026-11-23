FROM rncp-bc3-api:9
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY scripts/backup.py /app/scripts/backup.py
USER 10001
ENTRYPOINT ["python"]
