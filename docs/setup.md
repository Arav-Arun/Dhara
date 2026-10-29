# Setup

[← Back to the README](../README.md)

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20 or later
- About 10 GB of disk for the sources, the database and the index (the judgment PDFs can be deleted once processed)
- An OpenAI API key; search, section pages and draft checking work without one

## Install

```bash
git clone https://github.com/Arav-Arun/Dhara.git
cd Dhara
make setup                  # Python environment
npm --prefix web install    # site dependencies
cp .env.example .env        # then add your keys
```

## Build the data

| Command | What it does |
|---|---|
| `make statutes` | parse the six codes and check them against the official PDFs |
| `make mapping` | the official old-to-new correspondence, subsection rows kept |
| `make judgments` | download the Supreme Court criminal judgments (~4.4 GB, resumable), chunk them, extract citations |
| `make index` | retrieval units, BM25 and bge-m3 vectors (resumable) |
| `make bench` | build DharaBench |
| `make train` | fine-tune the reranker |
| `make eval` | the ablation on dev, the scope threshold, then the test split |
| `make export` | the public dataset files in `data/release/` |

## Run

```bash
make api    # http://localhost:8787
make web    # http://localhost:3000
make lint   # Ruff and mypy
make test   # pytest
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | for answers | research answers, judgment briefs and questions about a judgment |
| `HF_TOKEN` | no | faster model downloads; publishing the model |
| `KAGGLE_API_KEY` | no | publishing the dataset |
| `DHARA_LLM_MODEL` | no | the answering model (default `gpt-6-luna`) |
| `DHARA_DAILY_USD` | no | the most the public site spends on the model per day (default 1) |
| `DHARA_ALLOWED_ORIGINS` | no | the site's address for CORS (default `*`) |
| `NEXT_PUBLIC_DHARA_API` | no | where the site finds the API (default `http://localhost:8787`) |

To host it, see [deployment](deploy.md).
