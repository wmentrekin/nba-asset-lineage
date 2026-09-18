"""Environment configuration for the lineage package."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    """Return DATABASE_URL from the environment, loading .env first.

    Raises:
        RuntimeError: if DATABASE_URL is not set.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in a local .env file or as a "
            "repo secret in CI."
        )
    return database_url
