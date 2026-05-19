import asyncio
from loguru import logger

import utils.dramatiq
from scrappers.category import NoonCategoryScraper
from controllers.category import NoonCategoryController
from utils.db import SessionLocal


# @dramatiq.actor(max_retries=3)
def scrape_noon_categories():
    logger.info("Brand scrapping is started....")
    asyncio.run(run_scraper())


async def run_scraper():
    scraper = NoonCategoryScraper()
    try:
        categories = await scraper.scrape()
        logger.info(f"Total categ fetched are: {len(categories)}")
        db = SessionLocal()

        for cat in categories:
            try:
                record = {
                    "categoryId": cat.get('parent_id') or cat.get('id'),
                    "categoryName": cat.get('code'),
                    "subCategoryId": cat.get('id'),
                    "subCategoryName": cat.get('name')
                }
                await NoonCategoryController.create(db=db, **record)
    
            except Exception as err:
                logger.exception(f'Error occurred while creating entry in database: {err}')

        logger.info(f"Categories saved in the database!!")

    finally:
        await scraper.proxy_client.close_all_sessions()