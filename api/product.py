from fastapi import APIRouter, HTTPException
from loguru import logger


from workers.product import run_product_scraper



router = APIRouter(prefix='/product')



@router.get('/run_scrapper')
async def run_scrapper():
    await run_product_scraper()
    return HTTPException(status_code=200, detail="Noon-Product Scrapping started succesfully!")


