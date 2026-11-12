# Evaluation

[← Back to the README](../README.md)

## DharaBench

The benchmark is built from the corpus itself (`dhara/bench.py`):

- **Precedent questions** are written in new-code terms and answered by a judgment that cites only the old codes. A second copy of each has its section numbers removed.
- **Statute questions** are in plain language, with graded relevant sections.
- **Out-of-scope questions** (civil, tax, family) test whether Dhara declines.

Judgments and provisions are split into train, dev and test by hash, so the reranker never trains on anything it is tested on. Each split has 450 precedent and about 100 statute questions, plus 20 out-of-scope ones. The first version had 150 precedent questions per split; tripling it changed which reranker wins (below).

With 450 questions, a recall figure carries about ±0.023 of noise (one standard error), so differences of a point or two between rows are not evidence of anything.

## Retrieval, test split

Each row adds one thing to the row above it.

| Setup | Right judgment in top 10 | Same, numbers removed | Statute nDCG@10 |
|---|---|---|---|
| Keyword search, question as typed | 0.28 | 0.37 | 0.75 |
| Plain RAG: dense search only, as in earlier IPC/BNS projects | 0.31 | 0.36 | 0.83 |
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
| bge-reranker-base fine-tuned, earlier training set | 0.42 | | | |
| bge-reranker-base fine-tuned, larger training set | 0.38 | 0.42 | 0.42 | 1.8 s |
| bge-reranker-v2-m3 fine-tuned | 0.38 | 0.41 | 0.44 | 4.8 s |
| **MiniLM distilled from the fine-tuned v2-m3 (live)** | 0.40 | **0.45** | 0.46 | **0.6 s** |
| bge-reranker-base fine-tuned, over the weighted fusion | 0.35 | 0.38 | 0.42 | 1.7 s |
| fine-tuned base, plain questions put into legal terms first | 0.38 | 0.41 | 0.36 | 1.8 s |

The live setup was chosen on dev, before looking at test: among rerankers fast enough for a CPU server, the off-the-shelf base, the earlier fine-tuned base and the MiniLM sit within one standard error of each other (0.40 to 0.42), so the fastest won. Test is reported only for the rows that were candidates. Full tables for both splits, including precedent MRR and multi-vector rescoring (0.27 on dev, a loss), are in [`eval/results/`](../eval/results/).

## What the numbers say

- **Reading section numbers through the mapping is the main gain.** Setting numbers aside in keyword search and searching the passages that cite the named sections or their counterparts lifts precedent recall from 0.28 to 0.40 on test. Plain dense RAG reaches 0.31.
- **Fusion helps statutes and plain-language questions but dilutes the citation graph.** It adds 0.08 to statute nDCG and 0.03 to questions without section numbers, and costs 0.05 on precedent questions that name a section. The live pipeline keeps the weighted fusion for statutes and reranks judgments from the even one.
- **Fine-tuning on mined pairs did not beat the off-the-shelf models.** On 150 questions the retrained base model looked like a clear win (0.43 on test against 0.38 for the fusion). On 450, the same model scores 0.42 on dev against 0.41 off the shelf, and the larger off-the-shelf v2-m3 beats every fine-tuned model (0.47). Doubling the training data, from 1,596 to 2,756 questions, and adding negatives that cite a neighbouring section of the same code (murder against culpable homicide or attempt) did not help either: 0.38 on dev. The likely cause is label noise. A passage marked negative is often a valid answer that simply isn't from the source judgment, and the benchmark has the same blind spot, counting only the source judgment as right.
- **Distillation kept the accuracy and cut the cost by five.** A MiniLM cross-encoder (22.7M parameters, against 568M for v2-m3) trained to reproduce the fine-tuned v2-m3's scores reranks 50 passages in 0.7 s on a laptop CPU, against 3.8 s for the base model and 12.9 s for v2-m3. It does as well as the base models on dev and best on test.
- **Two speed and quality ideas made things worse.** Rewriting questions without a section number into legal terms before search lowered recall on exactly those questions (0.43 to 0.38 on dev). Scoring the top 5 statutes instead of 20 for the scope check declined fewer out-of-scope questions (7 of 20 against 9). Both are off.
- **The same model checks scope, set to favour answering.** Its top score over the retrieved sections decides whether a question is about criminal law. The threshold, fitted on dev, answers 95% of in-scope questions and declines 9 of the 20 out-of-scope ones. A stricter threshold declines more but also turns away real questions, the worse failure: an off-topic question that gets through still only sees criminal-law passages, and every citation is checked.
- **8-bit weights are not faster on an Apple CPU.** Dynamic int8 quantisation made the base model slower on a laptop's ARM cores (3.8 s to 8.7 s for 50 passages); its effect on Cloud Run's x86 processors is measured separately.

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
