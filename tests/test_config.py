from dhara.config import ROOT, settings


def test_paths_live_under_repo() -> None:
    assert settings.raw_dir == ROOT / "data" / "raw"
    assert settings.processed_dir.parent == settings.data_dir


def test_secrets_are_masked() -> None:
    if settings.openai_api_key is not None:
        assert "sk-" not in repr(settings.openai_api_key)
