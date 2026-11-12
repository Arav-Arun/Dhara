# Evaluation

[← Back to the README](../README.md)

## DharaBench

The benchmark is built from the corpus itself (`dhara/bench.py`):

- **Precedent questions** are written in new-code terms and answered by a judgment that cites only the old codes. A second copy of each has its section numbers removed.
- **Statute questions** are in plain language, with graded relevant sections.
- **Out-of-scope questions** (civil, tax, family) test whether Dhara declines.

Judgments and provisions are split into train, dev and test by hash, so the reranker never trains on anything it is tested on. Each split has 450 precedent and about 100 statute questions, plus 20 out-of-scope ones.

With 450 questions, a recall figure carries about ±0.023 of noise (one standard error), so differences of a point or two between rows are not evidence of anything.

## Retrieval, test split

Each row adds one thing to the row above it.

| Setup | Right judgment in top 10 | Same, numbers removed | Statute nDCG@10 |
|---|---|---|---|
| Keyword search, question as typed | 0.28 | 0.37 | 0.75 |
| Plain RAG: dense search only, as in other IPC/BNS projects | 0.31 | 0.36 | 0.83 |
| Keyword search, section numbers set aside | 0.37 | 0.37 | 0.75 |
| + citation graph | 0.40 | 0.37 | 0.75 |
| + bge-m3 dense and sparse, fused by rank | 0.36 | 0.40 | 0.83 |
| + citation graph weighted ×2 | 0.38 | 0.40 | 0.83 |

## Reranking the top 50

All over the even four-way fusion unless noted. Median time per search on a T4 GPU; the LLM's is mostly waiting on the API.

| Reranker | Dev, top 10 | Test, top 10 | Test, numbers removed | Median time |
|---|---|---|---|---|
| bge-reranker-base, off the shelf | 0.41 | | | 2.0 s |
| bge-reranker-v2-m3, off the shelf | **0.47** | | | 4.6 s |
| LLM reranker (gpt-6-luna) | 0.40 | 0.40 | 0.45 | 12.6 s |
| bge-reranker-base, fine-tuned | 0.38 | 0.42 | 0.42 | 1.8 s |
| bge-reranker-v2-m3, fine-tuned (the teacher) | 0.38 | 0.41 | 0.44 | 4.8 s |
| MiniLM distilled from the fine-tuned v2-m3 | 0.40 | 0.45 | 0.46 | **0.6 s** |
| **MiniLM, its order fused with the retrieval order (live)** | **0.43** | **0.44** | **0.47** | **0.6 s** |
| bge-reranker-base fine-tuned, over the weighted fusion | 0.35 | 0.38 | 0.42 | 1.7 s |

The live setup was chosen on dev, and test was scored afterwards. Among rerankers fast enough for a CPU server, the base-sized models and the MiniLM sit within one standard error of each other on dev (0.38 to 0.41), so the fastest is served. Its order is then fused by rank with the four retrievers' order (reciprocal rank fusion, k=60, the same constant as the first stage), which costs under a millisecond and raises precedent MRR from 0.21 to 0.25 on test. Full tables for both splits, with precedent MRR, are in [`eval/results/`](../eval/results/).

## Everyday questions

DharaBench questions are written from headnotes, so they are cleaner than what people type. A second set (`eval/dharabench/everyday.jsonl`) has 40 questions written the way a client or a junior lawyer would ask them, mostly without a section number, each answered by a landmark Supreme Court judgment: Lalita Kumari on registering an FIR, Arnesh Kumar on arrest in 498A cases, Gian Singh on quashing after a settlement, Bachan Singh on the death penalty, and so on. None of the 40 judgments was the source of a training question. A result counts only if the landmark itself is in the top 10, though later judgments applying it often answer the question too.

| Setup | Landmark in top 10 | In top 50 | MRR |
|---|---|---|---|
| Keyword search, question as typed | 0.80 | 0.88 | 0.34 |
| Plain RAG: dense search only | 0.68 | 0.95 | 0.39 |
| Four retrievers fused by rank | 0.88 | 0.95 | 0.41 |
| MiniLM order alone | 0.65 | 0.95 | 0.29 |
| **MiniLM order fused with the retrieval order (live)** | **0.83** | 0.95 | 0.38 |

With 40 questions a figure carries about ±0.06 of noise. `make eval` scores this set after the test split.

## What the numbers say

- **Reading section numbers through the mapping is the main gain.** Setting numbers aside in keyword search and searching the passages that cite the named sections or their counterparts lifts precedent recall from 0.28 to 0.40 on test. Plain dense RAG reaches 0.31.
- **Fusion helps statutes and plain-language questions but dilutes the citation graph.** It adds 0.08 to statute nDCG and 0.03 to questions without section numbers, and costs 0.05 on precedent questions that name a section. The live pipeline keeps the weighted fusion for statutes and reranks judgments from the even one.
- **The reranker's order is fused with the retrievers', not swapped for it.** Landmark judgments are quoted at length by later ones, and a cross-encoder reading one passage at a time tends to rank the quote above the source. Fusing the two orders keeps a judgment all four retrievers agree on near the top: on the everyday set the landmark is in the top 10 for 33 of 40 questions against 26 on the reranker's order alone, and on DharaBench dev precedent recall rises from 0.40 to 0.43. On short everyday questions the retrievers alone do as well (35 of 40, within the noise); the reranker's gain is on the longer DharaBench questions, 0.36 to 0.44 on test.
- **A distilled MiniLM is as accurate as rerankers many times its size.** The MiniLM cross-encoder (22.7M parameters) is trained to reproduce the scores of a bge-reranker-v2-m3 (568M) fine-tuned on pairs mined from training-split judgments. It reranks 50 passages in 0.7 s on a laptop CPU, against 3.8 s for the base model and 12.9 s for v2-m3, matches the base-sized models on dev and scores best on test. Off the shelf, v2-m3 scores higher on dev (0.47), but at that speed it cannot serve a CPU-only API.
- **The same model checks scope, set to favour answering.** Its top score over the retrieved sections decides whether a question is about criminal law. The threshold, fitted on dev, answers 95% of in-scope questions and declines 9 of the 20 out-of-scope ones. A stricter threshold declines more but also turns away real questions, the worse failure: an off-topic question that gets through still only sees criminal-law passages, and every citation is checked.

## Training

Training questions are written the same way as the benchmark's, from train-split judgments and sections only: 3,188 questions, of which 2,756 give at least one positive and negative, about 14,200 pairs. bge-reranker-base trained for two epochs on a MacBook (about 5 hours on its GPU). bge-reranker-v2-m3 trained for one epoch on a free Kaggle T4 in 23 minutes, and the MiniLM learned its scores on the same pairs.

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
make train   # mine pairs and fine-tune the reranker (dhara train --model large | mini for the others)
make eval    # dev ablation, the scope threshold, then the test split
```
