from fastapi import APIRouter, HTTPException
from loguru import logger



router = APIRouter(prefix='/category')


@router.get('/run_scrapper')
async def run_scrapper():
    return HTTPException(status_code=200, detail="Noon-Category Scrapping started succesfully!")