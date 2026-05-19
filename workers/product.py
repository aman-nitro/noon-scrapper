import asyncio
from loguru import logger

import utils.dramatiq

from scrappers.product import NoonProductScraper
from controllers.category import NoonCategoryController
from models.product import NoonProduct
from models.merchant import NoonMerchant
from utils.db import SessionLocal


BATCH_SIZE = 1000


# @dramatiq.actor(max_retries=3)
def scrape_noon_products():
    logger.info("Product scraping started...")
    asyncio.run(run_product_scraper())


async def run_product_scraper():
    async with SessionLocal() as db:
        categories = await NoonCategoryController.get_all(db=db)
        logger.info(f"Total categories fetched: {len(categories)}")

        product_batch = []
        merchant_names = set()
        total_inserted = 0

        for category in categories:
            logger.info(f"Starting scraping for category: {category.subCategoryName}")

            try:
                product_scraper = NoonProductScraper()
                products = await product_scraper.scrape(category=category.categoryName)

                logger.info(f"Total products fetched: {len(products)}")

                for product in products:
                    try:
                        merchant_name = product.get("store_name")
                        if merchant_name:
                            merchant_names.add(merchant_name)

                        product_batch.append(
                            NoonProduct(
                                name=product.get("name"),
                                brandId="",
                                sku=product.get("sku"),
                                product_url=product.get("url"),
                                imageUrl=product.get("image_url"),
                                price=product.get("price"),
                                inventory=product.get("stock_minimum_quantity"),
                                categoryId=category.categoryId,
                                subCategoryId=category.subCategoryId,
                                merchant_name=merchant_name,
                            )
                        )

                        if len(product_batch) >= BATCH_SIZE:
                            db.add_all(product_batch)
                            await db.commit()
                            total_inserted += len(product_batch)
                            logger.info(f"Inserted {total_inserted} products")

                            await db.flush()
                            product_batch.clear()

                    except Exception as err:
                        logger.exception(f"Error creating product entity: {err}")

            except Exception as err:
                logger.exception(f"Error scraping category: {err}")

        if product_batch:
            db.add_all(product_batch)
            await db.commit()
            total_inserted += len(product_batch)
            logger.info(f"Final inserted products count: {total_inserted}")


        merchant_batch = []
        for merchant_name in merchant_names:
            merchant_batch.append(NoonMerchant(name=merchant_name))

        if merchant_batch:
            db.add_all(merchant_batch)
            await db.commit()
            logger.info(f"Inserted {len(merchant_batch)} merchants")

        logger.info("Scraping completed successfully")