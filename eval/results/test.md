| Config | Precedent R@10 | Precedent MRR | Same, no section numbers R@10 | Reverse R@10 | Statute nDCG@10 | Statute R@10 | p50 s |
|---|---|---|---|---|---|---|---|
| keyword search, query as typed | 0.28 | 0.146 | 0.373 | 0.667 | 0.745 | 0.928 | 0.006 |
| dense only, query as typed (plain RAG, as in prior IPC/BNS repos) | 0.313 | 0.189 | 0.362 | 0.833 | 0.831 | 1.0 | 0.326 |
| keyword search, section numbers set aside | 0.373 | 0.199 | 0.373 | 1.0 | 0.745 | 0.928 | 0.007 |
| + citation graph | 0.404 | 0.214 | 0.373 | 0.833 | 0.745 | 0.928 | 0.007 |
| + bge-m3 dense and sparse, fused by RRF | 0.358 | 0.175 | 0.402 | 1.0 | 0.83 | 0.959 | 0.341 |
| + LLM reranker (gpt-6-luna) | 0.396 | 0.276 | 0.447 | 1.0 | 0.963 | 0.99 | 13.765 |
| + fine-tuned bge-reranker-base | 0.418 | 0.193 | 0.418 | 1.0 | 0.808 | 1.0 | 1.7 |
| + fine-tuned bge-reranker-v2-m3 | 0.409 | 0.22 | 0.44 | 0.833 | 0.8 | 1.0 | 4.866 |
| + MiniLM distilled from the fine-tuned v2-m3 | 0.447 | 0.211 | 0.456 | 0.833 | 0.864 | 1.0 | 0.585 |
| + fusion with the citation graph weighted x2 | 0.378 | 0.191 | 0.402 | 0.833 | 0.83 | 0.959 | 0.34 |
| + fine-tuned bge-reranker-base over the weighted fusion | 0.38 | 0.16 | 0.418 | 1.0 | 0.808 | 1.0 | 1.754 |
| + MiniLM order fused with the retrieval order (live) | 0.444 | 0.249 | 0.469 | 1.0 | 0.902 | 1.0 | 0.794 |
