| Config | Precedent R@10 | Precedent MRR | Same, no section numbers R@10 | Reverse R@10 | Statute nDCG@10 | Statute R@10 | p50 s |
|---|---|---|---|---|---|---|---|
| keyword search, query as typed | 0.387 | 0.199 | 0.48 | 0.6 | 0.701 | 0.91 | 0.003 |
| dense only, query as typed (plain RAG, as in prior IPC/BNS repos) | 0.373 | 0.217 | 0.407 | 0.6 | 0.763 | 0.98 | 0.142 |
| keyword search, section numbers set aside | 0.48 | 0.262 | 0.48 | 0.8 | 0.701 | 0.91 | 0.004 |
| + citation graph | 0.513 | 0.291 | 0.48 | 0.8 | 0.701 | 0.91 | 0.004 |
| + bge-m3 dense and sparse, fused by RRF | 0.44 | 0.23 | 0.533 | 0.8 | 0.795 | 0.96 | 0.167 |
| + multi-vector rescoring | 0.327 | 0.148 | 0.527 | 0.8 | 0.83 | 0.97 | 8.04 |
| + cross-encoder (bge-reranker-base) | 0.453 | 0.264 | 0.507 | 0.8 | 0.791 | 0.97 | 3.651 |
| + cross-encoder (bge-reranker-v2-m3) | 0.553 | 0.357 | 0.54 | 0.6 | 0.859 | 0.98 | 12.547 |
| + LLM reranker (gpt-6-luna) | 0.453 | 0.337 | 0.547 | 0.8 | 0.938 | 0.97 | 9.877 |
| + fine-tuned cross-encoder, first version | 0.427 | 0.224 | 0.507 | 0.8 | 0.793 | 0.98 | 6.345 |
| + fusion with the citation graph weighted x2 | 0.467 | 0.249 | 0.533 | 0.8 | 0.795 | 0.96 | 0.24 |
| + fine-tuned cross-encoder over the weighted fusion, first version | 0.427 | 0.228 | 0.507 | 0.8 | 0.793 | 0.98 | 6.345 |
