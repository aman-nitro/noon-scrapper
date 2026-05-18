import dramatiq
from dramatiq.brokers.redis import RedisBroker
from constants import NOON_REDIS_HOST, NOON_REDIS_PORT

redis_broker = RedisBroker(
    host=NOON_REDIS_HOST,
    port=NOON_REDIS_PORT,
    db=0,
    password = None
)

dramatiq.set_broker(redis_broker)