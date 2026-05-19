import asyncio
from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func

from scrappers.product import NoonProductScraper
from controllers.category import NoonCategoryController
from models.product import NoonProduct
from models.merchant import NoonMerchant
from utils.db import SessionLocal

BATCH_SIZE = 1000


def scrape_noon_products():
    logger.info("Product scraping started...")
    asyncio.run(run_product_scraper())


async def run_product_scraper():
    async with SessionLocal() as db:
        categories = await NoonCategoryController.get_all(db=db)
        logger.info(f"Total categories fetched: {len(categories)}")

        product_batch = []
        merchant_names = set()
        total_processed = 0

        for category in categories:
            logger.info(f"Scraping category: {category.subCategoryName}")

            try:
                product_scraper = NoonProductScraper()
                products = await product_scraper.scrape(category=category.categoryName)

                logger.info(f"Fetched {len(products)} products")

                for product in products:
                    try:
                        merchant_name = product.get("store_name")
                        if merchant_name:
                            merchant_names.add(merchant_name)

                        product_batch.append({
                            "name": product.get("name"),
                            "brandId": "",
                            "sku": product.get("sku"),
                            "product_url": product.get("url"),
                            "imageUrl": product.get("image_url"),
                            "price": product.get("price") or 0,
                            "inventory": product.get("stock_minimum_quantity") or 0,
                            "categoryId": category.categoryId,
                            "subCategoryId": category.subCategoryId,
                            "merchant_name": merchant_name or "",
                        })

                        if len(product_batch) >= BATCH_SIZE:
                            await upsert_products(db, product_batch)
                            total_processed += len(product_batch)
                            logger.info(f"Upserted {total_processed} products")
                            product_batch.clear()

                    except Exception as err:
                        logger.exception(f"Error processing product: {err}")

            except Exception as err:
                logger.exception(f"Error scraping category: {err}")

        if product_batch:
            await upsert_products(db, product_batch)
            total_processed += len(product_batch)
            logger.info(f"Final upserted products: {total_processed}")

        merchant_batch = [NoonMerchant(name=name) for name in merchant_names]

        if merchant_batch:
            db.add_all(merchant_batch)
            await db.commit()
            logger.info(f"Inserted {len(merchant_batch)} merchants")

        logger.info("Scraping completed successfully")


def dedupe_by_sku(product_batch):
    seen = set()
    unique = []

    for p in product_batch:
        sku = p["sku"]
        if not sku:
            continue

        if sku in seen:
            continue

        seen.add(sku)
        unique.append(p)

    return unique

async def upsert_products(db, product_batch):
    product_batch = dedupe_by_sku(product_batch)

    stmt = insert(NoonProduct).values(product_batch)

    stmt = stmt.on_conflict_do_update(
        index_elements=["sku"],
        set_={
            "name": stmt.excluded.name,
            "brandId": stmt.excluded.brandId,
            "product_url": stmt.excluded.product_url,
            "imageUrl": stmt.excluded.imageUrl,
            "price": stmt.excluded.price,
            "inventory": stmt.excluded.inventory,
            "categoryId": stmt.excluded.categoryId,
            "subCategoryId": stmt.excluded.subCategoryId,
            "merchant_name": stmt.excluded.merchant_name,
            "updatedAt": func.now(),
        },
    )

    await db.execute(stmt)
    await db.commit()