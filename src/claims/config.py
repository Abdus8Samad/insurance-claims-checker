"""Application configuration, loaded from environment (.env) with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

try:  # optional; .env is convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AppConfig:
    auth_mode: str = "api_key"  # "service_account" | "api_key"
    sa_path: Optional[str] = None
    location: str = "us-central1"
    api_key: Optional[str] = None
    model: str = "gemini-3.5-flash"
    policy_path: str = str(REPO_ROOT / "config" / "policy_terms.json")
    audit_dir: str = str(REPO_ROOT / "data" / "audit")
    request_timeout_ms: int = 120_000
    # Injectable clock for the submission-deadline check. None => use real today() in the UI.
    as_of_date: Optional[date] = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            auth_mode=os.getenv("GEMINI_AUTH_MODE", "api_key"),
            sa_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            location=os.getenv("VERTEX_LOCATION", "us-central1"),
            api_key=os.getenv("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            policy_path=os.getenv("POLICY_PATH", str(REPO_ROOT / "config" / "policy_terms.json")),
            audit_dir=os.getenv("AUDIT_DIR", str(REPO_ROOT / "data" / "audit")),
        )
