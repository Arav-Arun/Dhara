# Deploying Dhara

[← Back to the README](../README.md)

Two pieces: the site (Next.js, on Vercel) and the API (FastAPI with the index in memory, on Google Cloud Run). The live site is [dhara.aravarun.in](https://dhara.aravarun.in).

## What the API needs

| | Size | In memory |
|---|---|---|
| `data/processed/dhara.sqlite` | 0.8 GB | read through SQLite's page cache |
| `data/processed/index/` (`bm25/`, `dense.npy`, `sparse.npz`, `meta.json`; not `shards/`) | 0.65 GB | about 0.7 GB |
| fine-tuned reranker ([AravArun/dhara-reranker](https://huggingface.co/AravArun/dhara-reranker)) | 1.1 GB | about 1.1 GB |
| bge-m3 query encoder, without its ONNX export | 2.3 GB | about 2.3 GB |
| `eval/results/` (Method page tables, abstention threshold) | small | — |

Plan for about 5 GB of RAM, which rules out the 512 MB free tiers.

## API on Google Cloud Run

Cloud Run scales to zero, so the API costs nothing while nobody is using it, and occasional traffic stays inside the monthly free tier. There is no disk to mount, so [`deploy/cloudrun.Dockerfile`](../deploy/cloudrun.Dockerfile) puts the database, the index and both models in the image, and `DHARA_PRELOAD=1` loads them during start-up. The only standing cost is storing the ~4 GB image in Artifact Registry.

Once, in a Google Cloud project with billing:

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
grep '^OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d "\"'\n" | gcloud secrets create dhara-openai-key --data-file=-
```

Grant the project's default compute service account `roles/secretmanager.secretAccessor` and `roles/artifactregistry.writer`. Then, for each release:

```bash
sh deploy/cloudrun.sh
```

It uploads only what the image needs, builds it with Cloud Build, deploys to `asia-south1` with at most one instance, and deletes the previous image. The reranker is CPU-bound: on gen2 with 8 vCPUs a research answer takes about 55 seconds, against about 150 on the 2-vCPU default, and torch has to be told the vCPU count (`OMP_NUM_THREADS`) or it sizes its thread pool from the host. The first request after an idle spell waits for the instance to start; the site's `Waking` notice covers that.

The same API also runs anywhere Docker does with the root [`Dockerfile`](../Dockerfile), which mounts `data/` instead of baking it in:

```bash
docker build -t dhara-api .
docker run -p 8787:8787 -v "$PWD/data:/app/data" --env-file .env dhara-api
```

## Site on Vercel

Import the repo with `web/` as the root directory and set `NEXT_PUBLIC_DHARA_API` to the API's address. The build does not need the API: pages fill in their counts once it answers. For a custom domain, add it to the project and point a DNS-only CNAME at the target Vercel gives.

## Settings

| Variable | Default | |
|---|---|---|
| `OPENAI_API_KEY` | none | needed for answers, briefs and questions about a judgment |
| `DHARA_DAILY_USD` | 1.0 | the most the public site spends on the model per day |
| `DHARA_ALLOWED_ORIGINS` | `*` | the site's address, comma-separated if several |
| `DHARA_PRELOAD` | false | load the index and models at start-up instead of on the first question |
| `NEXT_PUBLIC_DHARA_API` | `http://localhost:8787` | where the site finds the API |
