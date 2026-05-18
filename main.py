from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from fastapi import FastAPI
from api import product

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started successfully")
    #$scheduler.add_job("", trigger="interval", minutes=5, max_instances=1)
    #scheduler.start()
    logger.info("Scheduler started")

    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped!!")


app = FastAPI(
    title="Noon Scrapper",
    description="Noon scrapper service that scrappes product, category, brands, store, etc.",
    version='1.0.1',
    lifespan=lifespan
    )



app.include_router(product.router, prefix='/api', tags=['product'])


@app.get('/')
async def noon_health():
    return {"status": "Noon service is running"}