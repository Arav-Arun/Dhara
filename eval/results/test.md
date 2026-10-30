| Config | Precedent R@10 | Precedent MRR | Same, no section numbers R@10 | Reverse R@10 | Statute nDCG@10 | Statute R@10 | p50 s |
|---|---|---|---|---|---|---|---|
| keyword search, query as typed | 0.267 | 0.127 | 0.36 | 0.667 | 0.745 | 0.928 | 0.007 |
| dense only, query as typed (plain RAG, as in prior IPC/BNS repos) | 0.313 | 0.208 | 0.367 | 0.833 | 0.831 | 1.0 | 0.789 |
| keyword search, section numbers set aside | 0.36 | 0.174 | 0.36 | 1.0 | 0.745 | 0.928 | 0.005 |
| + citation graph | 0.373 | 0.196 | 0.36 | 0.833 | 0.745 | 0.928 | 0.007 |
| + bge-m3 dense and sparse, fused by RRF | 0.333 | 0.148 | 0.413 | 1.0 | 0.83 | 0.959 | 0.754 |
| + LLM reranker (gpt-6-luna) | 0.367 | 0.264 | 0.473 | 1.0 | 0.952 | 0.99 | 9.712 |
| + fine-tuned cross-encoder, first version | 0.36 | 0.174 | 0.46 | 0.833 | 0.837 | 1.0 | 6.351 |
| + fusion with the citation graph weighted x2 | 0.38 | 0.18 | 0.413 | 0.833 | 0.83 | 0.959 | 0.239 |
| + fine-tuned cross-encoder over the weighted fusion, first version | 0.353 | 0.147 | 0.46 | 0.833 | 0.837 | 1.0 | 6.351 |
| + fine-tuned cross-encoder, retrained (live) | 0.433 | 0.214 | 0.447 | 0.833 | 0.816 | 1.0 | 5.459 |
| + fine-tuned cross-encoder, retrained, over the weighted fusion | 0.373 | 0.149 | 0.447 | 0.833 | 0.816 | 1.0 | 6.105 |
