| Config | R@10 | R@50 | MRR | p50 s |
|---|---|---|---|---|
| keyword search, query as typed | 0.8 | 0.875 | 0.341 | 0.003 |
| dense only, query as typed (plain RAG, as in prior IPC/BNS repos) | 0.675 | 0.95 | 0.385 | 0.12 |
| + citation graph | 0.8 | 0.875 | 0.341 | 0.003 |
| + bge-m3 dense and sparse, fused by RRF | 0.875 | 0.95 | 0.408 | 0.137 |
| + MiniLM distilled from the fine-tuned v2-m3 | 0.65 | 0.95 | 0.286 | 0.664 |
| + MiniLM order fused with the retrieval order (live) | 0.825 | 0.95 | 0.377 | 0.707 |
