.PHONY: setup check-env lint test statutes mapping judgments index bench train eval api web

setup:            ## install Python env and dev tools
	uv sync

check-env:        ## verify OpenAI / Hugging Face / Kaggle credentials
	uv run dhara check-env

lint:             ## ruff + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:             ## unit tests
	uv run pytest -q

statutes:         ## parse the six codes into data/processed/dhara.sqlite and verify against the PDFs
	uv run dhara build-statutes
	uv run dhara verify-statutes

mapping:          ## official IPC/CrPC/IEA <-> BNS/BNSS/BSA mapping from the NCRB tables
	uv run dhara build-mapping

judgments:        ## download SC criminal judgments (~5 GB, resumable) and build chunks + citations
	uv run dhara fetch-judgments
	uv run dhara build-judgments
	uv run dhara eval-citations

index:            ## retrieval units, BM25, bge-m3 dense + sparse (resumable)
	uv run dhara index

bench:            ## DharaBench dev/test queries (resumable, ~$0.15 of API calls)
	uv run dhara bench

train:            ## fine-tune the cross-encoder reranker
	uv run dhara train

eval:             ## dev ablation, the abstention threshold, the test split, then the everyday questions
	uv run dhara evaluate --split dev
	uv run dhara calibrate
	uv run dhara evaluate --split test
	uv run dhara everyday

api:              ## local API on :8787
	uv run uvicorn dhara.api:app --port 8787

web:              ## local site on :3000
	npm --prefix web run dev
