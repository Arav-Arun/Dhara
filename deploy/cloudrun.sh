#!/bin/sh
# Build the API image with Cloud Build and deploy it to Cloud Run.
# usage: sh deploy/cloudrun.sh   (needs gcloud logged in, project set, OPENAI_API_KEY in the
# dhara-openai-key secret; see docs/deploy.md)
set -e
PROJECT=$(gcloud config get-value project)
REGION=asia-south1
IMAGE=$REGION-docker.pkg.dev/$PROJECT/dhara/dhara-api:$(git rev-parse --short HEAD)
ORIGINS=${DHARA_ALLOWED_ORIGINS:-https://dhara.aravarun.in}

# only what the image needs, as copy-on-write clones (no extra disk on APFS)
CTX=$(mktemp -d)
trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/data/processed" "$CTX/eval"
cp -c pyproject.toml uv.lock "$CTX/"
cp -cR dhara deploy "$CTX/"
cp -cR eval/results "$CTX/eval/"
cp -c data/processed/dhara.sqlite "$CTX/data/processed/"
cp -cR data/processed/index "$CTX/data/processed/"
rm -rf "$CTX/data/processed/index/shards"
find "$CTX" -name __pycache__ -prune -exec rm -rf {} +

gcloud artifacts repositories describe dhara --location $REGION >/dev/null 2>&1 \
  || gcloud artifacts repositories create dhara --repository-format docker --location $REGION
gcloud builds submit "$CTX" --config deploy/cloudbuild.yaml --substitutions "_IMAGE=$IMAGE"
# the uploaded source (~0.9 GB) is only needed during the build
gcloud storage rm "gs://${PROJECT}_cloudbuild/source/**" --quiet || true

# One instance at most caps the bill, and request-based billing makes idle time free. The
# reranker is CPU-bound: gen2 and 8 vCPUs bring an answer from ~150 s to ~55 s, and torch must be
# told the vCPU count or it sizes its thread pool from the host's cores.
gcloud run deploy dhara-api --image "$IMAGE" --region $REGION --execution-environment gen2 \
  --cpu 8 --memory 8Gi --cpu-boost --concurrency 8 --min-instances 0 --max-instances 1 --timeout 300 \
  --allow-unauthenticated --set-secrets OPENAI_API_KEY=dhara-openai-key:latest \
  --set-env-vars "^|^DHARA_DAILY_USD=1|DHARA_ALLOWED_ORIGINS=$ORIGINS|OMP_NUM_THREADS=8|MKL_NUM_THREADS=8|TOKENIZERS_PARALLELISM=false"

# each image is ~4 GB of paid storage: keep only the one in use
gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT/dhara/dhara-api" --format 'value(version)' \
  | grep -v "$(gcloud artifacts docker images describe "$IMAGE" --format 'value(image_summary.digest)')" \
  | while read -r digest; do
      gcloud artifacts docker images delete "$REGION-docker.pkg.dev/$PROJECT/dhara/dhara-api@$digest" --delete-tags --quiet
    done
