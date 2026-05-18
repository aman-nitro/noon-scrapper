from fastapi import APIRouter, HTTPException
from loguru import logger

from workers.category import run_scraper



router = APIRouter(prefix='/category')


@router.get('/run_scrapper')
async def run_scrapper1():
    await run_scraper()
    return HTTPException(status_code=200, detail="Noon-Category Scrapping started succesfully!")