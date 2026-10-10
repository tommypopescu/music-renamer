FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ca-certificates tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/

# Upgrade pip + force-upgrade transitive deps with known CVEs
# setuptools and urllib3 are pip internals not overridden by requirements.txt alone
RUN pip install --no-cache-dir --upgrade pip setuptools==83.0.0 urllib3==2.8.0 msgpack==1.2.1

# Install app dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["/app/entrypoint.sh"]
