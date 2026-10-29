# Architecture

[← Back to the README](../README.md)

## The system

```mermaid
flowchart LR
    subgraph Sources
        N[NCRB Sankalan<br>BNS, BNSS, BSA, mapping tables]
        IC[India Code PDFs<br>IPC, CrPC, Evidence Act]
        SC[AWS Open Data<br>Supreme Court judgments]
    end
    subgraph Build["Build (dhara CLI)"]
        P[statutes, mapping]
        J[judgments: chunk, extract citations]
        X[index: BM25, bge-m3 dense and sparse]
        T[bench, train, evaluate]
    end
    N --> P
    IC --> P
    SC --> J
    P --> DB[(SQLite)]
    J --> DB
    DB --> X
    X --> T
    DB --> API[FastAPI]
    X --> API
    API --> W[Next.js site]
    API <--> L[OpenAI model]
```

Everything structured (statutes, the mapping, judgments, citations) lives in one SQLite file. The vectors are a NumPy matrix and a SciPy sparse matrix, and BM25 is a `bm25s` index. At about 215k retrieval units they all fit in memory, so search is exact and no vector database or ANN index is needed. The same files run on a laptop and in production.

## Answering a question

```mermaid
flowchart TD
    Q[question and earlier turns] --> W[rewrite a follow-up as a standalone question]
    W --> E[read section numbers, add their old/new counterparts from the official tables]
    E --> S[statutes and judgments searched as separate pools]
    S --> R[BM25 ∥ citation graph ×2 ∥ bge-m3 dense ∥ bge-m3 sparse, fused by rank]
    R --> CE[fine-tuned cross-encoder: is this a criminal-law question?]
    CE -->|no| D[decline]
    CE -->|yes| F[up to 2 follow-up searches, if the model asks for them]
    F --> B[context budget: statutes whole, at most 2 passages per judgment]
    B --> G[structured answer: every point cites passage ids]
    G --> V[deterministic verifier]
    V --> A[research note and trace, streamed to the site]
```

| Stage | Code |
|---|---|
| Rewrite, follow-up searches, trace | `dhara/agent.py` |
| Counterparts, retrievers, rank fusion | `dhara/retrieve.py` |
| Scope check and the baseline rerankers | `dhara/rerank.py`, `dhara/train_reranker.py` |
| Context budget and structured answer | `dhara/generate.py` |
| Verifier | `dhara/verify.py` |
| Judgment search, briefs, questions about a judgment | `dhara/library.py` |
| Draft checking and date rules | `dhara/checker.py`, `dhara/rules.py` |

## Design choices

- **Section numbers go to the citation graph, not to keyword search.** A question about BNS 103 is mapped to IPC 302, and one retriever searches only the judgment passages that cite either. In keyword search the same numbers hurt, because judgments mostly use the old ones: "103" matches the wrong documents.
- **The citation graph counts twice in the fusion.** With four retrievers weighted equally, dense and sparse search dilute it. The weight was fixed before measuring and helps on both evaluation splits.
- **The mapping is data, not a model's guess.** Old-to-new links come from NCRB's official tables, with their relation type (renumbered, merged, split, partly moved, new, dropped). Courts' own "corresponding to" phrases are an independent check (94% agreement).
- **One section, one chunk.** Statutes are retrieved whole, split only at subsection boundaries, so a proviso never loses the clause it qualifies. Judgments are chunked by numbered paragraph, so an answer can point at "paras 12–14".
- **The verifier is code.** It drops any statement that cites a passage it wasn't given, names a section that doesn't exist, or presents a repealed section as current law. If more than half the statements fail, Dhara declines to answer.
- **A bounded agent.** After the first search the model may ask for at most two more, through the same retriever, and every call is in the trace. There is no framework and no open-ended loop, so cost and latency stay predictable.
- **Rerankers are measured, not assumed.** Three were tried; none beat the weighted fusion at finding old-code precedent on both splits (see [evaluation](evaluation.md)). The fine-tuned one decides whether a question is in scope instead.
- **Which code applies is a rule.** The offence date decides substantive law; the date proceedings began decides procedure and evidence (BNSS s.531, BSA s.170).
- **Sexual-offence judgments are included.** The official reports anonymise victims, and leaving out 780 judgments left a gap in an area lawyers search often. They carry a `sensitive` flag, so a deployment can filter them.

## Reading a judgment

```mermaid
flowchart LR
    Q[query] --> S{library.search}
    S -->|section| C[citations of it or its counterpart]
    S -->|name or citation| N[judgment record]
    S -->|topic| R[hybrid retrieval over judgment passages]
    J[one judgment] --> BR[library.brief: facts, issue, held, cite it for]
    J --> AS[library.ask: retrieval inside the judgment, then an answer]
    J --> RE[library.related: headnote as the query]
```

Briefs and answers about a judgment cite its paragraphs as P1, P2 and so on, and the same rule applies: a point citing a paragraph the model wasn't given is dropped. Each brief is generated once and stored.

## Data model

```mermaid
erDiagram
    acts ||--o{ provisions : contains
    provisions ||--o{ provision_parts : "split into"
    provisions ||--o{ section_map : "old_id / new_id"
    provisions ||--o{ offence_classification : "First Schedule"
    judgments ||--o{ judgment_chunks : "passages"
    judgment_chunks ||--o{ citations : cites
    citations }o--|| provisions : resolves
    judgments ||--o{ bridges : "court links old and new"
    judgments ||--o| briefs : "generated once"
```

## Modules

| File | What it does |
|---|---|
| `statutes_ncrb.py`, `statutes_pdf.py`, `statutes.py`, `grammar.py` | the six codes from NCRB HTML and India Code PDFs, split into citable parts and checked against the PDFs |
| `mapping_tables.py`, `mapping.py` | NCRB's correspondence tables, compared with public mapping datasets |
| `judgments.py`, `citations.py` | Supreme Court judgments: select, download, chunk, extract section references |
| `index.py`, `retrieve.py` | retrieval units, BM25 and bge-m3 vectors; four retrievers and rank fusion |
| `rerank.py`, `train_reranker.py` | cross-encoder, multi-vector and LLM rerankers; fine-tuning on mined pairs |
| `generate.py`, `verify.py`, `agent.py` | context budget, structured answers, the verifier, the research pipeline |
| `library.py`, `checker.py`, `rules.py` | judgment search and briefs, draft checking, which code applies |
| `bench.py`, `evaluate.py`, `release.py` | DharaBench, the ablation runner, the dataset export |
| `api.py`, `cli.py`, `config.py`, `db.py`, `llm.py`, `models.py` | the API, the command line, settings, storage, the one place that calls the model |
