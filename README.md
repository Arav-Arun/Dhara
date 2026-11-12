<div align="center">
  
# Dhara

**A retrieval-augmented research system for Indian criminal law, built for the 2024 change of codes.**

It finds Supreme Court precedent under the old and the new section numbers at once, answers from it, and checks every citation in code before it is shown.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Model on Hugging Face](https://img.shields.io/badge/model-dhara--reranker-yellow?logo=huggingface)](https://huggingface.co/AravArun/dhara-reranker)
[![Dataset on Hugging Face](https://img.shields.io/badge/dataset-IPC%20to%20BNS-yellow?logo=huggingface)](https://huggingface.co/datasets/AravArun/dhara-indian-criminal-law)

<img src="docs/screenshots/demo.gif" width="100%" alt="A question about BNS 316 typed into Dhara, answered with cited judgments while the trace fills in" />
</div>

## The problem

On 1 July 2024 the Bharatiya Nyaya Sanhita, Nagarik Suraksha Sanhita and Sakshya Adhiniyam replaced the IPC, CrPC and Evidence Act, and every section got a new number. The judgments a lawyer relies on still cite the old ones: in Supreme Court criminal judgments decided after July 2024, old-code citations outnumber new ones about 19 to 1. A search for "BNS 103" misses the 3,455 judgments on IPC 302, and plain dense RAG finds the right judgment for only 31% of such questions.

## How it works

```mermaid
flowchart LR
    Q[question] --> E[section numbers read<br>in both codes]
    E --> R[BM25 ∥ citation graph ∥<br>bge-m3 dense ∥ sparse]
    R --> F[fused by rank]
    F --> X[distilled MiniLM reranks,<br>fused with that order]
    X --> C{in scope?<br>same model}
    C -->|yes| G[structured answer,<br>every point cited]
    C -->|no| D[decline]
    G --> V[verifier<br>in code]
    V --> A[research note<br>and trace]
```

1. **A citation graph across both numberings.** Section numbers in a question are mapped to their counterparts through NCRB's official correspondence tables, and one retriever searches only the judgment passages that cite either. A question about BNS 103 reaches the judgments on IPC 302.
2. **Hybrid retrieval, fused by rank.** That retriever runs alongside BM25 (with section numbers set aside, since judgments mostly use the old ones) and bge-m3 dense and sparse search, merged by reciprocal rank fusion.
3. **A small distilled reranker that also gates scope.** A MiniLM cross-encoder (22.7M parameters), distilled from a bge-reranker-v2-m3 fine-tuned on the corpus, rereads the top 50 judgment passages on a CPU-only server, and its order is fused by rank with the retrievers' order, so a judgment every retriever agrees on keeps that weight. Its score over the retrieved statutes decides whether a question is about criminal law at all; if not, Dhara declines.
4. **Answers that can't cite what they weren't given.** The model writes a structured answer from the retrieved passages only, and may run at most two more searches, each shown in the trace. Code, not a model, then drops any statement that cites a passage it wasn't given, names a section that doesn't exist, or presents a repealed section as current law. Checked parts stream to the page as they are written.

**More:** [architecture and design choices](docs/architecture.md)

## Results

DharaBench, built from the corpus, has 1,148 questions with known answers in held-out dev and test splits. On the 450 test questions whose answer is a Supreme Court judgment, many of them asked with new-code numbers about a judgment that cites only the old code:

| Setup | Right judgment in top 10 |
|---|---|
| Keyword search, question as typed | 0.28 |
| Plain RAG (dense search only) | 0.31 |
| Keyword search + citation graph | 0.40 |
| LLM reranker over the four retrievers | 0.40 |
| Fine-tuned bge-reranker-base over the four retrievers | 0.42 |
| **Live: four retrievers + distilled MiniLM, orders fused** | **0.44** |

A second set has 40 questions typed the way people ask them, mostly without a section number ("police station refusing to write my FIR, they say they will do an enquiry first"), each answered by a landmark judgment such as Lalita Kumari or Arnesh Kumar that no training question was written from:

| Setup | Landmark judgment in top 10 |
|---|---|
| Plain RAG (dense search only) | 0.68 (27 of 40) |
| Keyword search, question as typed | 0.80 (32 of 40) |
| **Live** | **0.83 (33 of 40)** |

- **The citation graph is the main gain:** 0.28 to 0.40 before any model reranks.
- **The reranker's order is fused with the retrievers', not swapped for it.** Later judgments quote landmarks at length, and a cross-encoder reading one passage at a time tends to prefer the quote. Fusing its order with the retrieval order keeps a judgment that all four retrievers agree on: 33 of 40 landmarks in the top 10 against 26 on the reranker's order alone, and 0.43 against 0.40 on DharaBench dev. On short everyday questions the four retrievers alone already find 35 of 40; the reranker earns its place on the longer, more specific DharaBench questions, 0.36 to 0.44 on test.
- **A 22.7M-parameter reranker on a CPU.** The MiniLM is distilled from a bge-reranker-v2-m3 fine-tuned on the corpus, a model 25 times its size, and matches the base-sized rerankers at a fifth of their compute. Full research answers take about 20 to 30 seconds on the live site.

**More:** [benchmark, full ablation and component checks](docs/evaluation.md)

## What it does

- **Research.** Ask in your own words or by section. The answer reads like a research note: the law, what the courts have held, and the cases to cite, each with the proposition it supports, its year and report citation. Follow-up questions keep the context.
- **Judgments.** Search by section (old or new number), case name, citation or topic. Each judgment opens with a cited brief, answers questions from its own text, and marks every old section in it with today's number.
- **Section pages.** Any section, old or new, through ⌘K: its text, its counterpart in the other code, and the judgments on it.

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/landing.webp" width="100%" /><br>Home: ask a question or open a tool</td>
    <td width="50%"><img src="docs/screenshots/research.webp" width="100%" /><br>Research: a cited research note, the cases to cite and the trace of every search</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/judgment.webp" width="100%" /><br>A judgment: cited brief, the provisions it turns on in today's numbers, related judgments</td>
    <td width="50%"><img src="docs/screenshots/judgments.webp" width="100%" /><br>Judgments: search by section, name, citation or topic, with filters</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/section.webp" width="100%" /><br>Section page: the text, its counterpart in the other code and the judgments on it</td>
    <td width="50%"><img src="docs/screenshots/method.webp" width="100%" /><br>Method: how a question is answered, step by step, with the measured results</td>
  </tr>
</table>

## Getting started

```bash
git clone https://github.com/Arav-Arun/Dhara.git && cd Dhara
make setup && npm --prefix web install && cp .env.example .env
make statutes mapping judgments index    # build the data (~4.4 GB download, resumable)
make api                                 # http://localhost:8787
make web                                 # http://localhost:3000
```

**More:** [setup, scripts and settings](docs/setup.md)

## Project structure

```
dhara/     Python package: ingestion, retrieval, reranking, generation, verification, evaluation, API
web/       Next.js site
eval/      DharaBench questions and results
tests/     pytest suite
docs/      architecture, evaluation, setup
```
