from fastapi import APIRouter
from loguru import logger
from workers.brand import run_scraper

router = APIRouter(prefix='/brand')


@router.get('/run_scrapper')
async def run_scrapper():
    logger.info(f"Starting brand scrapper")
    await run_scraper()
    return {"status": "Noon-Brand Scrapping started succesfully!"}

