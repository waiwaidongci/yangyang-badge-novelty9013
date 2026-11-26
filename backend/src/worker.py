import logging
import time

from redis import RedisError

from src.config.settings import ARTIFACT_DIR
from src.config.database import Session
from src.services.execution import (
    claim,
    claim_recommendation,
    execute,
    execute_recommendation,
    recover_jobs,
)
from src.services.queue import QUEUE_KEY, redis_client
from src.services.recommendations import recover_interrupted


def heartbeat():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / 'worker.heartbeat').touch()


def worker():
    logging.basicConfig(level=logging.INFO)
    recover_jobs()
    with Session() as session:
        recover_interrupted(session)
    while True:
        heartbeat()
        job = claim()
        if job is not None:
            execute(job)
            continue
        advice_job = claim_recommendation()
        if advice_job is not None:
            execute_recommendation(advice_job)
            continue
        try:
            redis_client.brpop(QUEUE_KEY, timeout=2)
        except RedisError:
            time.sleep(1)


if __name__ == '__main__':
    worker()
