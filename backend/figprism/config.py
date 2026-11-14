from functools import lru_cache
from pathlib import Path
import os
import secrets
from pydantic import BaseModel, Field, SecretStr
import yaml

ROOT = Path(os.environ.get("FIGPRISM_ROOT", Path(__file__).resolve().parents[2]))


class WebDAVConfig(BaseModel):
    url: str = ""
    username: str = ""
    password: SecretStr = SecretStr("")
    root: str = "/figprism"


class VisionConfig(BaseModel):
    driver: str = "codex_subagent"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr = SecretStr("")
    model: str = "gpt-4.1-mini"


class PipelineConfig(BaseModel):
    metadata: int = Field(default=4, ge=1, le=16)
    download: int = Field(default=3, ge=1, le=8)
    papers: int = Field(default=2, ge=1, le=4)
    cpu: int = Field(default=2, ge=1, le=4)
    cpu_threads: int = Field(default=1, ge=1, le=4)
    vision: int = Field(default=3, ge=1, le=8)
    upload: int = Field(default=4, ge=1, le=12)
    figures: int = Field(default=6, ge=1, le=12)
    per_paper_figures: int = Field(default=3, ge=1, le=6)
    retry_attempts: int = Field(default=3, ge=1, le=5)
    arxiv_interval: float = Field(default=3.0, ge=3, le=60)


class Settings(BaseModel):
    data_dir: Path = ROOT / "data"
    domains_file: Path = ROOT / "config/domains.yaml"
    secret_key: SecretStr
    public_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    webdav: WebDAVConfig = Field(default_factory=WebDAVConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    layout_model: str | None = None
    hf_min_upvotes: int = 20
    cache_max_bytes: int = 2 * 1024**3
    max_pdf_bytes: int = 50 * 1024**2


@lru_cache
def get_settings():
    path = Path(os.environ.get("FIGPRISM_CONFIG", ROOT / "config/local.yaml"))
    values = yaml.safe_load(path.read_text()) if path.exists() else {}
    values = values or {}
    for env, key in [
        ("FIGPRISM_DATA_DIR", "data_dir"),
        ("FIGPRISM_SECRET_KEY", "secret_key"),
        ("FIGPRISM_PUBLIC_ORIGIN", "public_origin"),
        ("FIGPRISM_LAYOUT_MODEL", "layout_model"),
    ]:
        if os.environ.get(env):
            values[key] = os.environ[env]
    if "FIGPRISM_COOKIE_SECURE" in os.environ:
        values["cookie_secure"] = os.environ["FIGPRISM_COOKIE_SECURE"].lower() == "true"
    data = Path(values.get("data_dir", ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    if not values.get("secret_key"):
        keyfile = data / ".secret_key"
        try:
            with keyfile.open("x") as f:
                keyfile.chmod(0o600)
                f.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        values["secret_key"] = keyfile.read_text()
    settings = Settings(**values)
    if len(settings.secret_key.get_secret_value()) < 32:
        raise ValueError("secret_key must be at least 32 characters")
    return settings
