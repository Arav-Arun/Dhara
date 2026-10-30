"""Export the public dataset (Kaggle and Hugging Face): Parquet files plus a data card.

Nothing here is uploaded; `dhara export` writes data/release/ for a human to review first.
Judgment text is not included (it is in the source dataset); judgment records, the citation
graph and the courts' own old-to-new links are.
"""

import json
import shutil

import polars as pl

from dhara import db
from dhara.config import ROOT, settings

OUT = settings.data_dir / "release"

TABLES = {
    "provisions": "SELECT id, act, number, heading, chapter_no, chapter_title, subheading, text, status, flag "
    "FROM provisions",
    "provision_parts": "SELECT id, provision_id, ord, kind, label, text, status, added, changed, deleted "
    "FROM provision_parts",
    "mapping": "SELECT new_id, old_id, relation, changed, note, similarity, tags, in_reverse FROM section_map",
    "mapping_rows": "SELECT new_id, new_sub, old_id, old_sub, status, changed, note, raw_new, raw_old "
    "FROM mapping_rows",
    "classification": "SELECT * FROM offence_classification",
    "court_bridges": "SELECT judgment_id, new_id, old_id, snippet FROM bridges",
    "judgments": "SELECT id, title, decided_on, citation, court, source_path AS source_file FROM judgments",
    "citations": "SELECT judgment_id, chunk_id, provision_id, act, section, sub, raw FROM citations WHERE resolved = 1",
}

# what each file and column is: written into the card and into Kaggle's per-file metadata
FILES = {
    "provisions": "Every section of the six codes, with chapter, status and full text",
    "provision_parts": "Sections split into citable parts: subsections, provisos, explanations, illustrations",
    "mapping": "NCRB's official old-to-new correspondence, one row per old/new pair",
    "mapping_rows": "The same correspondence tables at subsection level, as published",
    "classification": "BNSS First Schedule: punishment, cognizable, bailable and which court tries each offence",
    "judgments": "Supreme Court of India criminal judgments, 1950 to September 2026",
    "citations": "Every section reference found in a judgment, resolved to a provision",
    "court_bridges": "Places where the Court itself links an old section to its new counterpart",
}
COLUMNS = {
    "id": "Provision or judgment id, e.g. BNS:103 or 2013INSC164",
    "act": "Code: BNS, BNSS, BSA (new) or IPC, CRPC, IEA (old)",
    "number": "Section number within the code",
    "heading": "Section heading",
    "chapter_no": "Chapter number",
    "chapter_title": "Chapter title",
    "subheading": "Heading of the group of sections, where the code has one",
    "text": "Full text",
    "status": "in_force, repealed or omitted",
    "flag": "Parsing note, if any",
    "provision_id": "Provision id, e.g. IPC:302",
    "ord": "Order of the part within its section",
    "kind": "subsection, proviso, explanation, illustration or text",
    "label": "Label as printed, e.g. (1) or (a)",
    "added": "Words added relative to the old code (JSON list), from NCRB's annotations",
    "changed": "Changed words (JSON list) or 1 if the provision changed",
    "deleted": "Words deleted relative to the old code (JSON list)",
    "new_id": "Provision id in the new code",
    "old_id": "Provision id in the old code",
    "relation": "equivalent, merged, split, partial, new or omitted",
    "note": "NCRB's note on the change",
    "similarity": "Text similarity between the old and new section",
    "tags": "Kinds of change (JSON list)",
    "in_reverse": "1 if NCRB's reverse table lists the same pair",
    "new_sub": "Subsection in the new code",
    "old_sub": "Subsection in the old code",
    "raw_new": "The new-code cell as published",
    "raw_old": "The old-code cell as published",
    "sub": "Subsection, if given",
    "offence": "Offence as described in the First Schedule",
    "punishment": "Punishment",
    "cognizable": "Cognizable or non-cognizable",
    "bailable": "Bailable or non-bailable",
    "triable_by": "Court by which the offence is triable",
    "title": "Case name",
    "decided_on": "Date of the judgment",
    "citation": "Report citation, e.g. [2013] 2 S.C.R. 921",
    "court": "Supreme Court of India",
    "source_file": "PDF name in the source dataset",
    "judgment_id": "Judgment id",
    "chunk_id": "Passage id: judgment id and paragraph-group number",
    "section": "Section number as cited",
    "raw": "The citation phrase as written in the judgment",
    "snippet": "The sentence in which the Court links the two sections",
}
BENCH_COLUMNS = {
    "id": "Question id",
    "type": "precedent, precedent_reverse, statute or abstain (out of scope)",
    "split": "dev or test",
    "query": "The question",
    "relevant_judgments": "Judgment ids that answer it (precedent questions)",
    "provisions_in_query": "Sections named in the question",
    "cited_by_judgment": "Sections the answering judgment cites",
    "exclude_units": "Passages to leave out of retrieval: the headnote the question was written from",
    "relevant_provisions": "Answering sections, graded: 2 = the section, 1 = its counterpart",
}

FRONT = """---
license: cc-by-4.0
language: [en]
pretty_name: "Dhara: Indian criminal law, IPC to BNS, with Supreme Court judgments"
tags: [legal, law, india, criminal-law, ipc, bns, supreme-court, citation-graph, retrieval, rag, benchmark]
task_categories: [text-retrieval, question-answering]
size_categories: [100K<n<1M]
configs:
{configs}
---
"""

CARD = """# Dhara: Indian criminal law, IPC to BNS, with Supreme Court judgments

On 1 July 2024 India replaced the Indian Penal Code, the Code of Criminal Procedure and the Evidence
Act with the Bharatiya Nyaya Sanhita (BNS), Bharatiya Nagarik Suraksha Sanhita (BNSS) and Bharatiya
Sakshya Adhiniyam (BSA). Every section got a new number, but the judgments lawyers rely on still cite
the old ones. This dataset connects the two: all six codes, the official old-to-new mapping, and every
section reference in {judgments:,} Supreme Court criminal judgments.

| File | Rows | What it is |
|---|---|---|
{files}
| dharabench_dev.jsonl, dharabench_test.jsonl | {bench} | Retrieval benchmark: questions with known answers |

## Quick start

```python
import pandas as pd

mapping = pd.read_parquet("mapping.parquet")
cites = pd.read_parquet("citations.parquet")

mapping[mapping.old_id == "IPC:302"]          # BNS:103, equivalent
cites[cites.provision_id.isin(["IPC:302", "BNS:103"])].judgment_id.nunique()   # 3455 judgments on murder
cites.provision_id.value_counts().head()      # the most-cited sections
```

On Hugging Face, each file is also a config: `load_dataset("AravArun/dhara-indian-criminal-law", "mapping")`.

## What you can do with it

- Look up what replaced any IPC, CrPC or Evidence Act section, down to the subsection.
- Find every Supreme Court judgment on a section under either numbering.
- Study the citation network: which sections the Court relies on, and how that changes by decade.
- See exactly what changed in each section (`provision_parts`: added, changed and deleted words).
- Classify offences (cognizable, bailable, which court) from the BNSS First Schedule.
- Benchmark legal retrieval or train rerankers and embeddings with DharaBench.

## DharaBench

{bench} questions in dev and test splits. Precedent questions are phrased with new-code section numbers
and answered by a judgment that cites only the old code; a statute slice asks plain-language questions
answered by a section; an out-of-scope slice (civil, tax, family) should be declined. Questions are
generated from each judgment's headnote and the official mapping; judgments and provisions are split
by hash, so no split shares one. Baselines on the test split, right judgment in the top 10:

| Retrieval | Recall@10 |
|---|---|
| BM25, question as typed | 0.27 |
| Dense only (bge-m3) | 0.31 |
| BM25 + citation graph over the mapping | 0.37 |
| BM25 + citation graph (x2) + bge-m3 dense and sparse, rank fusion | 0.38 |
| + top 50 reranked by a [fine-tuned cross-encoder](https://huggingface.co/AravArun/dhara-reranker) | 0.43 |

## Columns

{columns}

## Sources and licence

Statutes and the correspondence tables come from NCRB Sankalan and India Code; Indian statutes are
not protected by copyright. Judgment records and citations are derived from the Indian Supreme Court
Judgments dataset by Dattam Labs (AWS Open Data, CC-BY-4.0); the judgment text itself is in that
dataset, and `source_file` names the PDF. This dataset is released under CC-BY-4.0.

Try it live: https://dhara.aravarun.in

Code, method and full results: https://github.com/Arav-Arun/Dhara
"""


def _columns() -> str:
    out = []
    for name in TABLES:
        cols = pl.read_parquet_schema(OUT / f"{name}.parquet")
        out.append(f"**{name}**: " + "; ".join(f"`{c}`: {COLUMNS.get(c, '')}" for c in cols))
    return "\n\n".join(out)


def _kaggle(counts: dict[str, int]) -> dict[str, object]:
    resources: list[dict[str, object]] = []
    for name in TABLES:
        schema = pl.read_parquet_schema(OUT / f"{name}.parquet")
        fields = [
            {
                "name": c,
                "description": COLUMNS.get(c, ""),
                "type": "integer" if t.is_integer() else "number" if t.is_float() else "string",
            }
            for c, t in schema.items()
        ]
        resources.append(
            {
                "path": f"{name}.parquet",
                "description": f"{FILES[name]} ({counts[name]:,} rows)",
                "schema": {"fields": fields},
            }
        )
    for split in ("dev", "test"):
        resources.append(
            {
                "path": f"dharabench_{split}.jsonl",
                "description": f"DharaBench {split} split: retrieval questions with known answers",
                "schema": {
                    "fields": [{"name": c, "description": d, "type": "string"} for c, d in BENCH_COLUMNS.items()]
                },
            }
        )
    return {
        "title": "IPC to BNS: Indian Criminal Law & SC Judgments",
        "subtitle": "Six criminal codes, the official old-to-new mapping, 159k SC judgment citations",
        "id": f"{settings.kaggle_username}/dhara-indian-criminal-law",
        "licenses": [{"name": "CC-BY-4.0"}],
        "keywords": ["law", "india", "nlp", "text"],
        "resources": resources,
    }


def export() -> dict[str, int]:
    con = db.connect()
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, sql in TABLES.items():
        rows = con.execute(sql).fetchall()
        cols = [d[0] for d in con.execute(sql + " LIMIT 0").description]
        pl.DataFrame([dict(zip(cols, r, strict=True)) for r in rows], infer_schema_length=None).write_parquet(
            OUT / f"{name}.parquet"
        )
        counts[name] = len(rows)
    bench_n = 0
    for split in ("dev", "test"):  # flat files: Kaggle doesn't keep folders
        src = ROOT / "eval" / "dharabench" / f"{split}.jsonl"
        shutil.copy(src, OUT / f"dharabench_{split}.jsonl")
        bench_n += len(src.read_text().splitlines())
    shutil.rmtree(OUT / "dharabench", ignore_errors=True)
    (OUT / "counts.json").unlink(missing_ok=True)
    files = "\n".join(f"| {n}.parquet | {counts[n]:,} | {FILES[n]} |" for n in TABLES)
    configs = "\n".join(f"  - config_name: {n}\n    data_files: {n}.parquet" for n in TABLES)
    card = CARD.format(**counts, files=files, bench=f"{bench_n:,}", columns=_columns())
    (OUT / "README.md").write_text(FRONT.format(configs=configs) + card)
    kaggle = _kaggle(counts) | {"description": card}
    (OUT / "dataset-metadata.json").write_text(json.dumps(kaggle, indent=2, ensure_ascii=False))
    return counts
