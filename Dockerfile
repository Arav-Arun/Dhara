# The API. The data (database, index, fine-tuned reranker) is mounted, not baked in: it is about
# 2.5 GB and changes only when the corpus is rebuilt. bge-m3 is fetched once into the HF cache volume.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/cache/huggingface

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY dhara ./dhara
COPY eval/results ./eval/results
RUN uv sync --frozen --no-dev

EXPOSE 8787
# Caddy on the host forwards each visitor's address; trusting it is safe because the port is
# published on 127.0.0.1 only, and without it every visitor shares one rate limit
CMD ["uv", "run", "--no-dev", "uvicorn", "dhara.api:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers", "--forwarded-allow-ips", "*"]
