from fastapi import APIRouter, HTTPException
from loguru import logger



router = APIRouter(prefix='/product')



@router.get('/run_scrapper')
async def run_scrapper():
    return HTTPException(status_code=200, detail="Noon-Product Scrapping started succesfully!")


