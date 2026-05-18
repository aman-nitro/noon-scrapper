import asyncio
from loguru import logger

import utils.dramatiq
from scrappers.category import NoonCategoryScraper
from controllers.brand import NoonBrandService
from utils.db import SessionLocal


# @dramatiq.actor(max_retries=3)
def scrape_noon_categories():
    logger.info("Brand scrapping is started....")
    asyncio.run(run_scraper())


async def run_scraper():
    scraper = NoonCategoryScraper()
    try:
        categories = await scraper.scrape()
        logger.info(categories)
        logger.info(f"Total categ fetched are: {len(categories)}")
        logger.info(f"Categories scrapped: {categories}")

        # db = SessionLocal()

        try:
            pass
            

        except Exception as err:
            logger.exception(f'Error occurred while creating entry in database')

    finally:
        await scraper.proxy_client.close_all_sessions()