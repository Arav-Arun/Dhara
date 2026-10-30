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
| + citation graph weighted ×2 | 0.38 | 0.41 | 0.83 | 0.2 s |

## Reranking the top 50

| Reranker | Over | Right judgment in top 10 | Same, numbers removed | Median time |
|---|---|---|---|---|
| LLM reranker (gpt-6-luna) | even fusion | 0.37 | 0.47 | 9.7 s |
| Fine-tuned cross-encoder, first version | even fusion | 0.36 | 0.46 | 6.4 s |
| Fine-tuned cross-encoder, first version | weighted fusion | 0.35 | 0.46 | 6.4 s |
| **Fine-tuned cross-encoder, retrained (live)** | **even fusion** | **0.43** | 0.45 | 5.5 s |
| Fine-tuned cross-encoder, retrained | weighted fusion | 0.37 | 0.45 | 6.1 s |

On dev the retrained model over the even fusion scores 0.49, against 0.47 for the weighted fusion and 0.43 for the first version. Two more baselines were measured on dev only: the larger off-the-shelf bge-reranker-v2-m3 did best (0.55, at 12.5 s per search, twice the size), and multi-vector rescoring hurt (0.33). Full tables for both splits are in [`eval/results/`](../eval/results/).

## What the numbers say

- **Reading section numbers through the mapping is the main gain.** Setting numbers aside in keyword search and searching the passages that cite the named sections or their counterparts lifts precedent recall from 0.27 to 0.37. Plain dense RAG reaches 0.31.
- **Fusion helps statutes and plain-language questions but dilutes the citation graph.** Counting the graph twice recovers it: 0.33 to 0.38 on test and 0.44 to 0.47 on dev. With 150 questions a recall figure carries about ±0.04 of noise, so the claim is that it helps on both splits, not by how much.
- **The first fine-tuned reranker lost because of its training data.** Its hard negatives included passages from other judgments citing the same sections as the question, which are often right answers too. It was taught a distinction the text can't support, and it lost to the plain fusion on both splits.
- **Retraining fixed that.** Negatives now come from the live four-way search, a passage citing the question's law is never one, and training runs two epochs at the 512-token passage length used in inference (the first version: one epoch at 320). Precedent recall on test went from 0.36 to 0.43, ahead of every retriever and the LLM reranker.
- **It helps over the even fusion and hurts over the weighted one.** Never having learned to rank one same-law passage above another, it can only reshuffle the weighted fusion's top 50, which the citation graph has already filled with exactly those passages. Over the even fusion it pulls in the right judgments that keyword and dense search found. So the live pipeline reranks judgments from the even fusion; statutes keep the weighted order, which ranks them better (0.83 against 0.82).
- **The same model checks scope, set to favour answering.** Its top score over the retrieved sections decides whether a question is about criminal law. The threshold, fitted on dev, answers 95% of in-scope questions (95% on test too) and declines half the out-of-scope ones (9 of 20 on test). The threshold with the best balanced accuracy declines 17 of 20 but also turns away a quarter of real questions, a worse failure: an off-topic question that gets through still only sees criminal-law passages, and every citation is checked.

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
make train   # mine pairs and fine-tune the reranker
make eval    # dev ablation, the scope threshold, then the test split
```
