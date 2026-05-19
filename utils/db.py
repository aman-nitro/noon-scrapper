from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from contextlib import contextmanager
from constants import NOON_PG_DATABASE_URL, NOON_REDIS_DB, NOON_REDIS_HOST, NOON_REDIS_PASSWORD, NOON_REDIS_PORT
import redis.asyncio as redis
from loguru import logger

engine = create_async_engine(NOON_PG_DATABASE_URL, echo=True, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session

        

redis_client: redis.Redis | None = None
sync_redis_client = None

logger.info("Initializing Redis connection...")

redis_client = redis.Redis(
    host=NOON_REDIS_HOST,
    port=NOON_REDIS_PORT,
    db=NOON_REDIS_DB,
    password=NOON_REDIS_PASSWORD,
    decode_responses=True
)

def get_redis() -> redis.Redis:
    return redis_client