# The API for Google Cloud Run. Same as ../Dockerfile, except that Cloud Run has no disk to mount,
# so the database, index and both models are inside the image, and they load during start-up.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/app/.cache/huggingface

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate > /tmp/all.txt \
    && grep -vE '^(torch|nvidia-|triton|cuda-)' /tmp/all.txt > /tmp/deps.txt \
    && uv pip install --system "$(grep '^torch==' /tmp/all.txt | cut -d' ' -f1)" --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system -r /tmp/deps.txt

# the same files dhara.index.embed_model asks for, so the offline start finds them all
RUN python -c "from huggingface_hub import snapshot_download as get; \
get('BAAI/bge-m3', ignore_patterns=['onnx/*', 'imgs/*', '*.jpg']); \
get('AravArun/dhara-reranker', local_dir='data/processed/models/dhara-reranker')"

COPY dhara ./dhara
COPY eval/results ./eval/results
COPY data/processed/dhara.sqlite data/processed/
COPY data/processed/index data/processed/index

ENV HF_HUB_OFFLINE=1 DHARA_PRELOAD=1
CMD exec uvicorn dhara.api:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'
