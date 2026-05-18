import asyncio
from loguru import logger

import utils.dramatiq
from scrappers.brand import NoonBrandScraper
from controllers.brand import NoonBrandService
from utils.db import SessionLocal


# @dramatiq.actor(max_retries=3)
def scrape_noon_brands():
    logger.info("Brand scrapping is started....")
    asyncio.run(run_scraper())


async def run_scraper():
    scraper = NoonBrandScraper()
    try:
        brands = await scraper.fetch_all_brands()
        logger.info(f"Total brands fetched are: {len(brands)}")
        unique_brands = scraper.deduplicate(brands)

        db = SessionLocal()

        try:
            for brand in unique_brands:
                logger.info(f'Adding {brand} in the database')
                await NoonBrandService.create(db, name=brand)

        except Exception as err:
            logger.exception(f'Error occurred while creating entry in database')

    finally:
        await scraper.proxy_client.close_all_sessions()