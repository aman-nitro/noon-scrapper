import os

NOON_PG_DATABASE_URL = os.getenv(
    "NOON_PG_DATABASE_URL", "postgresql://postgres:postgres@noon_pg:5432/assistant_pg")
NOON_REDIS_DB = os.getenv("NOON_REDIS_DB", "0")
NOON_REDIS_HOST = os.getenv("NOON_REDIS_HOST", "redis")
NOON_REDIS_PORT = os.getenv("NOON_REDIS_PORT", "6379")
NOON_REDIS_PASSWORD = os.getenv("NOON_REDIS_PASSWORD", "")
