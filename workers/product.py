import asyncio
from loguru import logger

import utils.dramatiq
from scrappers.product import NoonProductScraper

from controllers.category import NoonCategoryController
from controllers.product import NoonProductController
from controllers.merchant import NoonMerchantController
from utils.db import SessionLocal


# @dramatiq.actor(max_retries=3)
def scrape_noon_products():
    logger.info("Brand scrapping is started....")
    asyncio.run(run_product_scraper())


async def run_product_scraper():
    async with SessionLocal() as db:
        merchants = []
        
        categories = await NoonCategoryController.get_all(db=db)
        print(f"Total categories fetched are: {len(categories)}")

        for category in categories:
            logger.info(f"Starting scrapping for category: {category.subCategoryName}")
            try:
                product_scraper = NoonProductScraper()
                products = await product_scraper.scrape(category=category.subCategoryName)

                logger.info(f"Total brands fetched are: {len(products)}")
                

                for product in products:
                    try:
                        merchants.append(product.get('store_name'))
                        product_entity = {
                            "name":product.get('name'),
                            "brandId":"",
                            "sku": product.get('sku'),
                            "product_url": product.get('url'),
                            "imageUrl": product.get('image_url'),
                            "price": product.get('price'),
                            "inventory": product.get('stock_minimum_quantity'),
                            "categoryId": category.categoryId,
                            "subCategoryId": category.subCategoryId,
                            "merchant_name": product.get('store_name'),
                        }
                        await NoonProductController.create(db=db, **product_entity)
                    except Exception as err: 
                        logger.exception(f"Error occured while creating product in the database: {err}")
        
            except Exception as err:
                
                logger.exception(f'Error occurred while creating entry in database')
        
        for name in merchants:
            try:
                await NoonMerchantController.create(db=db, name=name)
            except Exception as err: 
                logger.exception(f"Error occured while creating merchant in the database: {err}")