# The API. The data (database, index, fine-tuned reranker) is mounted, not baked in: it is about
# 2.5 GB and changes only when the corpus is rebuilt. bge-m3 is fetched once into the HF cache volume.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 HF_HOME=/cache/huggingface

# versions come from uv.lock, but torch comes from the CPU-only index: the server has no GPU, and the
# default wheels pull in several GB of CUDA libraries
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate > /tmp/all.txt \
    && grep -vE '^(torch|nvidia-|triton|cuda-)' /tmp/all.txt > /tmp/deps.txt \
    && uv pip install --system "$(grep '^torch==' /tmp/all.txt | cut -d' ' -f1)" --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system -r /tmp/deps.txt
COPY dhara ./dhara
COPY eval/results ./eval/results

EXPOSE 8787
# the reverse proxy in front forwards each visitor's address; without it every visitor would
# share one rate limit (publish the port on 127.0.0.1 only, so nothing else can set the header)
CMD ["uvicorn", "dhara.api:app", "--host", "0.0.0.0", "--port", "8787", "--proxy-headers", "--forwarded-allow-ips", "*"]
