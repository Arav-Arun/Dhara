# Deploying Dhara

[← Back to the README](../README.md)

Two pieces: the site (Next.js) and the API (FastAPI with the index in memory).

## What the API needs

| | Size | In memory |
|---|---|---|
| `data/processed/dhara.sqlite` | 0.8 GB | read through SQLite's page cache |
| `data/processed/index/` (`bm25/`, `dense.npy`, `sparse.npz`, `meta.json`; not `shards/`) | 0.65 GB | about 0.7 GB |
| `data/processed/models/dhara-reranker/` (reranker and scope check) | 1.1 GB | about 1.1 GB |
| bge-m3 query encoder (downloaded to the HF cache on first start) | 2.2 GB | about 2.3 GB |
| `eval/results/` (Method page tables, abstention threshold) | small | — |

Plan for about 5 GB of RAM. That rules out 512 MB free tiers (Render's free plan included). An Oracle Cloud Always Free Ampere A1 machine (4 cores, 24 GB, free; a card is needed to sign up) fits comfortably.

## API on an Oracle Always Free machine

1. Create an Ampere A1 instance (Ubuntu 24.04, 4 OCPU, 24 GB). Open port 443 in the subnet's security list.
2. Install Docker and Caddy, then copy the data over:
   ```bash
   rsync -av --exclude shards --exclude checkpoints --exclude dhara-reranker-v1 \
     data/processed/ ubuntu@HOST:/srv/dhara/data/processed/
   ```
3. Build and run (on the machine, from a checkout of the repo):
   ```bash
   docker build -t dhara-api .
   docker run -d --restart unless-stopped -p 127.0.0.1:8787:8787 \
     -v /srv/dhara/data:/app/data -v /srv/dhara/hf:/cache/huggingface \
     -e OPENAI_API_KEY=... -e DHARA_DAILY_USD=1 -e DHARA_ALLOWED_ORIGINS=https://SITE \
     dhara-api
   ```
4. Caddy in front for HTTPS: a `Caddyfile` with `api.DOMAIN { reverse_proxy 127.0.0.1:8787 }`.

The first request after a start loads the index and the encoder (about a minute); the site shows "Starting up" meanwhile.

## Site on Vercel

Import the repo with `web/` as the root directory and set `NEXT_PUBLIC_DHARA_API=https://api.DOMAIN`. The build does not need the API: pages fill in their counts once it answers.

## Settings

| Variable | Default | |
|---|---|---|
| `OPENAI_API_KEY` | none | needed for answers, briefs and questions about a judgment |
| `DHARA_DAILY_USD` | 1.0 | the most the public site spends on the model per day |
| `DHARA_ALLOWED_ORIGINS` | `*` | the site's address, comma-separated if several |
| `NEXT_PUBLIC_DHARA_API` | `http://localhost:8787` | where the site finds the API |
