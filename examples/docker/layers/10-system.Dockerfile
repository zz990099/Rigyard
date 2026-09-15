RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates supervisor \
    && rm -rf /var/lib/apt/lists/*
