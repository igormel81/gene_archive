# gene-archive: build a site and serve it with relatives' comments.
#   docker build -t gene-archive .
#   docker run -p 8111:8111 -v "$PWD/my-family:/site" -v gene-state:/state gene-archive
# Optional: -e GENE_PIN=1234 (private archive), -e GENE_MODERATE=1, -e GENE_PREFIX=/family
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY gene_archive ./gene_archive
RUN pip install --no-cache-dir ".[images]" && useradd --system --home /state gene && mkdir -p /state && chown gene /state
USER gene
ENV GENE_STATE_DIR=/state GENE_TRUST_PROXY=1
EXPOSE 8111
VOLUME ["/state"]
# the site folder is mounted read-only; the build goes to /state/_site
CMD ["sh", "-c", "gene build /site -o /state/_site && gene serve /site --no-build -o /state/_site --host 0.0.0.0 --port 8111 --state /state"]
