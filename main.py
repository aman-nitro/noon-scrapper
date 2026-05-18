from fastapi import FastAPI
from api import product

app = FastAPI(
    title="Noon Scrapper",
    description="Noon scrapper service that scrappes product, category, brands, store, etc.",
    version='1.0.1'
    )



app.include_router(product.router, prefix='/api', tags=['product'])


@app.get('/health')
async def noon_health():
    return {"status": "Noon service is running"}