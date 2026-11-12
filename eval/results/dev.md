| Config | Precedent R@10 | Precedent MRR | Same, no section numbers R@10 | Reverse R@10 | Statute nDCG@10 | Statute R@10 | p50 s |
|---|---|---|---|---|---|---|---|
| keyword search, query as typed | 0.309 | 0.157 | 0.389 | 0.6 | 0.699 | 0.91 | 0.006 |
| dense only, query as typed (plain RAG, as in prior IPC/BNS repos) | 0.344 | 0.197 | 0.358 | 0.6 | 0.763 | 0.98 | 0.286 |
| keyword search, section numbers set aside | 0.389 | 0.213 | 0.389 | 0.8 | 0.699 | 0.91 | 0.006 |
| + citation graph | 0.402 | 0.229 | 0.389 | 0.8 | 0.699 | 0.91 | 0.006 |
| + bge-m3 dense and sparse, fused by RRF | 0.371 | 0.191 | 0.438 | 0.8 | 0.792 | 0.96 | 0.302 |
| + cross-encoder (bge-reranker-base) | 0.407 | 0.237 | 0.442 | 0.8 | 0.789 | 0.97 | 1.964 |
| + cross-encoder (bge-reranker-v2-m3) | 0.467 | 0.286 | 0.48 | 0.6 | 0.857 | 0.98 | 4.623 |
| + LLM reranker (gpt-6-luna) | 0.398 | 0.292 | 0.478 | 0.8 | 0.943 | 0.97 | 12.633 |
| + fine-tuned bge-reranker-base | 0.378 | 0.169 | 0.429 | 0.8 | 0.763 | 0.97 | 1.762 |
| + fine-tuned bge-reranker-v2-m3 | 0.38 | 0.199 | 0.464 | 0.6 | 0.782 | 0.97 | 4.83 |
| + MiniLM distilled from the fine-tuned v2-m3 | 0.404 | 0.183 | 0.413 | 0.6 | 0.826 | 0.97 | 0.582 |
| + fusion with the citation graph weighted x2 | 0.373 | 0.198 | 0.438 | 0.8 | 0.792 | 0.96 | 0.344 |
| + fine-tuned bge-reranker-base over the weighted fusion | 0.349 | 0.143 | 0.429 | 0.6 | 0.763 | 0.97 | 1.721 |
| + MiniLM order fused with the retrieval order (live) | 0.429 | 0.236 | 0.469 | 0.6 | 0.889 | 0.96 | 0.814 |
