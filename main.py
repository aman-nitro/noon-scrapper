from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import brand, category, product
import utils.dramatiq


app = FastAPI(
    title="Noon Scrapper",
    description="Noon scrapper service that scrappes product, category, brands, store, etc.",
    version='1.0.1',
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brand.router, prefix='/api', tags=['brand'])
app.include_router(category.router, prefix='/api', tags=['category'])
app.include_router(product.router, prefix='/api', tags=['product'])


@app.get('/')
async def noon_health():
    return {"status": "Noon service is running"}