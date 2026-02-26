FROM python:3.12-slim

# Minimal OS deps and init (tini)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy app and config template
COPY app/ /app/app/
COPY beets/config.template.yaml /app/beets/config.template.yaml
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["/app/entrypoint.sh"]
