# Evaluation

[← Back to the README](../README.md)

## DharaBench

The benchmark is built from the corpus itself (`dhara/bench.py`):

- **Precedent questions** are written in new-code terms and answered by a judgment that cites only the old codes. A second copy of each has its section numbers removed.
- **Statute questions** are in plain language, with graded relevant sections.
- **Out-of-scope questions** (civil, tax, family) test whether Dhara declines.

Judgments and provisions are split into train, dev and test by hash, so the reranker never trains on anything it is tested on. Each split has 150 precedent and about 100 statute questions.

## Retrieval, test split

Each row adds one thing to the row above it.

| Setup | Right judgment in top 10 | Same, numbers removed | Statute nDCG@10 | Median time |
|---|---|---|---|---|
| Keyword search, question as typed | 0.27 | 0.36 | 0.75 | < 0.01 s |
| Plain RAG: dense search only, as in earlier IPC/BNS projects | 0.31 | 0.37 | 0.83 | 0.8 s |
| Keyword search, section numbers set aside | 0.36 | 0.36 | 0.75 | < 0.01 s |
| + citation graph | 0.37 | 0.36 | 0.75 | < 0.01 s |
| + bge-m3 dense and sparse, fused by rank | 0.33 | 0.41 | 0.83 | 0.8 s |
| **+ citation graph weighted ×2 (live)** | **0.38** | 0.41 | 0.83 | 0.2 s |
| + LLM reranker (gpt-6-luna) over the fusion | 0.37 | 0.47 | 0.95 | 9.7 s |
| + fine-tuned cross-encoder over the fusion | 0.36 | 0.46 | 0.84 | 6.4 s |
| + fine-tuned cross-encoder over the weighted fusion | 0.35 | 0.46 | 0.84 | 6.4 s |

On dev, two more baselines were measured: the larger off-the-shelf bge-reranker-v2-m3 did best on precedent (0.55, at 12.5 s per search), and multi-vector rescoring hurt (0.33). Full tables for both splits are in [`eval/results/`](../eval/results/).

## What the numbers say

- **Reading section numbers through the mapping is the main gain.** Setting numbers aside in keyword search and searching the passages that cite the named sections or their counterparts lifts precedent recall from 0.27 to 0.37. Plain dense RAG reaches 0.31.
- **Fusion helps statutes and plain-language questions but dilutes the citation graph.** Counting the graph twice recovers it: 0.33 to 0.38 on test and 0.44 to 0.47 on dev, with statutes unchanged. With 150 questions a recall figure carries about ±0.04 of noise, so the claim is that it helps on both splits, not by how much.
- **Reranking didn't pay for itself on precedent.** The reranker fine-tuned on mined pairs (bge-reranker-base, one epoch) helps questions without section numbers on test (0.41 to 0.46) but loses on both kinds on dev, and adds about 6 s per search. The LLM reranker ranks statutes best (0.95) but takes about 10 s and costs money per query.
- **So the live pipeline answers from the weighted fusion.** The fine-tuned model has one job: its top statute score, calibrated on dev, decides whether a question is in scope, with a balanced accuracy of 0.88.

The likeliest way to make reranking earn its place is better training data: more hard negatives drawn from the citation graph.

## Components

| Component | Measured on | Result |
|---|---|---|
| Statute parsing | text found verbatim in the official PDFs | 96–100% per code; remaining misses are PDF page artifacts |
| Official mapping | agreement with NCRB's own reverse tables | 98.1–99.5% |
| Mapping vs GSMS-B public dataset | Jaccard over section pairs | 0.978–0.994 |
| Citation extractor | 40 held-out hand-labelled sentences | precision 0.96, recall 0.84 |
| Courts' own old/new links | agreement with the official mapping | 94% (46 of 49) |

## Reproducing

```bash
make bench   # build DharaBench (about $0.15 of model calls)
make train   # fine-tune the reranker
make eval    # dev ablation, the scope threshold, then the test split
```
