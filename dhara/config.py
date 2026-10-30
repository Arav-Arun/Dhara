"""Settings loaded from .env.

One place for paths, model ids, credentials and the public sources the corpus comes from,
so the rest of the code never reads environment variables directly."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    openai_api_key: SecretStr | None = None
    hf_token: SecretStr | None = None
    kaggle_api_key: SecretStr | None = None

    kaggle_username: str = "aravarun"

    dhara_llm_model: str = "gpt-6-luna"
    dhara_daily_usd: float = 1.0  # what the public site may spend on the model per day
    dhara_allowed_origins: str = "*"  # comma-separated; set to the site's address in production
    dhara_preload: bool = False  # load the index and models at start-up instead of on the first question
    dhara_embed_model: str = "BAAI/bge-m3"

    data_dir: Path = ROOT / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


settings = Settings()

# Public sources, linked from the site so every text can be checked against the original.
SC_BUCKET = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/"
INDIA_CODE_PDF = {  # the copies the old codes were parsed from; see data/raw/indiacode/manifest.jsonl
    "IPC": "https://indiacode.gov.in/server/api/core/bitstreams/337c7a03-60c6-4953-8dd6-90e65c343629/content",
    "IEA": "https://indiacode.gov.in/server/api/core/bitstreams/4a3677bf-e488-4689-bf30-6ae29255a3ba/content",
    "CRPC": "https://indiacode.gov.in/server/api/core/bitstreams/dad067ad-01e3-4227-97a5-60774c53939c/content",
}


def sc_pdf_url(year: str, path: str) -> str:
    """The bucket files each judgment under the year it was decided."""
    return f"{SC_BUCKET}data/pdf/year={year}/english/{path}_EN.pdf"
