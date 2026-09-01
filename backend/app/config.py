"""
Central configuration. All secrets are resolved from environment variables.

In production these can be injected via AWS Secrets Manager (e.g. through
ECS/Fargate task definitions or a Secrets Manager -> env sidecar). For local
development, they can simply be pasted into a local .env file -- nothing in
this codebase requires AWS to run locally; STORAGE_BACKEND=local (the
default) and LLM_PROVIDER=gemini/mock keep everything on your machine.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database -- SQLite by default (a single local file, zero setup).
    # Set DATABASE_URL to a postgresql+psycopg2://... URL for production/RDS.
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./jd_agent.db")

    # Storage: "local" (default, writes under ./storage_data, zero setup)
    # or "s3" (requires AWS credentials + a real bucket).
    storage_backend: str = os.environ.get("STORAGE_BACKEND", "local")  # "local" | "s3"
    local_storage_path: str = os.environ.get("LOCAL_STORAGE_PATH", "./storage_data")

    # S3 (only used when storage_backend="s3")
    s3_bucket: str = os.environ.get("S3_BUCKET", "jd-agent-artifacts")
    aws_region: str = os.environ.get("AWS_REGION", "us-east-1")

    # Queue (not required for local dev -- the API processes JDs inline;
    # this only matters if you run the standalone SQS worker).
    queue_backend: str = os.environ.get("QUEUE_BACKEND", "local")  # "local" | "sqs" | "redis"
    sqs_queue_url: str = os.environ.get("SQS_QUEUE_URL", "")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # LLM provider abstraction
    llm_provider: str = os.environ.get("LLM_PROVIDER", "mock")  # "mock" | "anthropic" | "gemini"
    # Leave unset (None) to let LLMService pick the right default model per
    # provider; only set LLM_MODEL if you want to override that.
    llm_model: Optional[str] = os.environ.get("LLM_MODEL") or None

    # LLM API keys -- paste directly into your local .env, never commit them.
    # In production, inject via AWS Secrets Manager / your secrets store instead.
    anthropic_api_key: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
    gemini_api_key: Optional[str] = os.environ.get("GEMINI_API_KEY")

    # Auth
    auth_provider: str = os.environ.get("AUTH_PROVIDER", "supabase")  # "supabase" | "auth0" | "cognito"

    # Misc
    environment: str = os.environ.get("ENVIRONMENT", "development")

    # extra="ignore" so any additional/unexpected env vars in a .env file
    # never crash startup with a pydantic ValidationError.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
