"""Command-line entry point: `uv run dhara <command>`."""

import sqlite3

import httpx
import typer

from dhara.config import settings

app = typer.Typer(no_args_is_help=True)


def _check(name: str, ok: bool, detail: str) -> bool:
    typer.echo(f"{'PASS' if ok else 'FAIL'}  {name:<8} {detail}")
    return ok


@app.command()
def check_env() -> None:
    """Verify each credential works. Prints pass/fail only, never the secret."""
    results = []

    key = settings.openai_api_key
    if key is None:
        results.append(_check("openai", False, "OPENAI_API_KEY missing"))
    else:
        r = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key.get_secret_value()}"},
            timeout=20,
        )
        if r.status_code == 200:
            ids = {m["id"] for m in r.json()["data"]}
            model = settings.dhara_llm_model
            found = "available" if model in ids else "NOT in model list"
            luna = sorted(i for i in ids if "luna" in i)
            results.append(_check("openai", model in ids, f"{model} {found}; luna models: {luna}"))
        else:
            results.append(_check("openai", False, f"HTTP {r.status_code}"))

    tok = settings.hf_token
    if tok is None:
        results.append(_check("hf", False, "HF_TOKEN missing"))
    else:
        r = httpx.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {tok.get_secret_value()}"},
            timeout=20,
        )
        if r.status_code == 200:
            d = r.json()
            role = d.get("auth", {}).get("accessToken", {}).get("role")
            results.append(_check("hf", role == "write", f"user={d.get('name')} role={role}"))
        else:
            results.append(_check("hf", False, f"HTTP {r.status_code}"))

    kk = settings.kaggle_api_key
    if kk is None:
        results.append(_check("kaggle", False, "KAGGLE_API_KEY missing"))
    else:
        r = httpx.get(
            "https://www.kaggle.com/api/v1/datasets/list",
            params={"user": settings.kaggle_username},
            headers={"Authorization": f"Bearer {kk.get_secret_value()}"},
            timeout=20,
        )
        if r.status_code != 200:
            r = httpx.get(
                "https://www.kaggle.com/api/v1/datasets/list",
                params={"user": settings.kaggle_username},
                auth=(settings.kaggle_username, kk.get_secret_value()),
                timeout=20,
            )
        results.append(_check("kaggle", r.status_code == 200, f"HTTP {r.status_code}"))

    raise typer.Exit(0 if all(results) else 1)


@app.command()
def build_statutes() -> None:
    """Parse the six codes and the BNSS First Schedule into data/processed/dhara.sqlite."""
    from dhara.statutes import build

    for k, v in build().items():
        typer.echo(f"{k:<20} {v}")


@app.command()
def verify_statutes() -> None:
    """Share of sections whose parsed text is found verbatim in the official PDF."""
    from dhara import db
    from dhara.statutes import check

    for act, (ok, n, misses) in check(db.connect()).items():
        typer.echo(f"{act:<5} {ok}/{n} = {ok / n:.1%}  misses: {', '.join(misses[:8])}")


@app.command()
def build_mapping() -> None:
    """Build the official old <-> new mapping (NCRB correspondence tables) into the database."""
    from dhara.mapping import build

    for act, stats in build().items():
        lists = {k: v for k, v in stats.items() if isinstance(v, list)}
        typer.echo(f"{act:<5} " + "  ".join(f"{k}={v}" for k, v in stats.items() if k not in lists))
        for k, v in lists.items():
            if v:
                typer.echo(f"      {k}: {', '.join(map(str, v))}")

    from dhara.mapping import compare_prior

    typer.echo("\ncompared with public mapping datasets (section pairs):")
    for r in compare_prior():
        typer.echo(
            f"  {r['dataset']:<13} {r['code']:<5} jaccard={r['jaccard']}  agree={r['agree']}  "
            f"only_ours={r['only_ours']} (many-to-one: {r['only_ours_in_many_to_one']})  "
            f"only_theirs={r['only_theirs']}"
        )


@app.command()
def fetch_judgments() -> None:
    """Download the criminal Supreme Court judgment PDFs (~5 GB, resumable)."""
    import asyncio

    from dhara.config import sc_pdf_url
    from dhara.judgments import download, sc_criminal

    out = settings.raw_dir / "aws_sc" / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    items = [(sc_pdf_url(year, path), out / f"{path}_EN.pdf") for _, year, path, *_ in sc_criminal()]
    ok, missing = asyncio.run(download(items))
    typer.echo(f"downloaded {ok}, missing {missing}")


@app.command()
def build_judgments() -> None:
    """Supreme Court criminal judgments -> chunks, citations, code bridges (needs the PDFs)."""
    from dhara.judgments import bridge_agreement, build

    for k, v in {**build(), **{f"bridges_{k}": v for k, v in bridge_agreement().items()}}.items():
        typer.echo(f"{k:<24} {v}")


@app.command()
def eval_citations() -> None:
    """Citation extractor precision/recall on the dev and held-out test sets."""
    from dhara.citations import DEV, TEST, evaluate

    for name, path in (("dev", DEV), ("test", TEST)):
        r = evaluate(path)
        typer.echo(f"{name:<5} precision={r['precision']} recall={r['recall']} f1={r['f1']}")


@app.command()
def export() -> None:
    """Write the public dataset to data/release/ (reviewed by hand before any upload)."""
    from dhara.release import export as run

    for k, v in run().items():
        typer.echo(f"{k:<16} {v}")


@app.command()
def index() -> None:
    """Build retrieval units, the BM25 index and bge-m3 vectors (resumable; hours on a laptop)."""
    from dhara import index as ix

    con = db_connect()
    typer.echo(f"units {ix.build_units(con)}")
    ix.build_bm25(con)
    typer.echo(f"encoded shards {ix.encode()}")
    typer.echo(str(ix.assemble()))


@app.command()
def bench() -> None:
    """Generate DharaBench dev and test queries (resumable)."""
    from dhara import bench as b

    typer.echo(str(b.build()))


@app.command()
def train() -> None:
    """Training queries → mined pairs → fine-tuned cross-encoder."""
    from dhara import train_reranker as tr
    from dhara.retrieve import Index

    typer.echo(f"queries {tr.make_queries()}")
    typer.echo(f"pairs {tr.mine(Index())}")
    typer.echo(f"model {tr.train()}")


@app.command()
def evaluate(split: str = "dev", only: str = "") -> None:
    """Run the ablation table on DharaBench; --only filters rows by name."""
    from dhara.evaluate import ablate
    from dhara.train_reranker import OUT_DIR

    model = str(OUT_DIR) if (OUT_DIR / "config.json").exists() else None  # the folder exists from the first checkpoint
    typer.echo(ablate(split, [o for o in only.split(",") if o] or None, finetuned=model))


@app.command()
def calibrate(split: str = "dev") -> None:
    """Fit the abstention threshold with the fine-tuned reranker; the API reads it at start-up."""
    import json

    from dhara.evaluate import RESULTS, calibrate_abstention
    from dhara.retrieve import Index
    from dhara.train_reranker import OUT_DIR

    out = calibrate_abstention(Index(), str(OUT_DIR), split)
    (RESULTS / "abstention.json").write_text(json.dumps(out, indent=2))
    typer.echo(out)


@app.command()
def llm_usage() -> None:
    """Tokens and estimated spend on the OpenAI API so far."""
    from dhara.llm import usage

    typer.echo(str(usage()))


def db_connect() -> "sqlite3.Connection":
    from dhara import db

    return db.connect()
