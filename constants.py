import os

NOON_PG_DATABASE_URL = os.getenv(
    "NOON_PG_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@noon_pg:5432/noon_pg")
NOON_REDIS_DB = os.getenv("NOON_REDIS_DB", "0")
NOON_REDIS_HOST = os.getenv("NOON_REDIS_HOST", "redis")
NOON_REDIS_PORT = int(os.getenv("NOON_REDIS_PORT", 6679))
NOON_REDIS_PASSWORD = os.getenv("NOON_REDIS_PASSWORD", "")


NOON_BASE_URL = 'https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u'