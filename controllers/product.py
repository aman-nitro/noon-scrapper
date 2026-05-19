from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from models.product import NoonProduct


class NoonProductController:

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> NoonProduct:
        record = NoonProduct(**kwargs)
        try:
            db.add(record)
            # await db.commit()
            # await db.refresh(record)
            return record
        except SQLAlchemyError as exc:
            # await db.rollback()
            raise RuntimeError(f"Failed to create NoonProduct: {exc}") from exc

    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int) -> Optional[NoonProduct]:
        result = await db.execute(select(NoonProduct).where(NoonProduct.id == record_id))
        return result.scalars().first()

    @staticmethod
    async def get_by_category_id(db: AsyncSession, category_id: int) -> list[NoonProduct]:
        result = await db.execute(select(NoonProduct).where(NoonProduct.categoryId == category_id))
        return result.scalars().all()

    @staticmethod
    async def get_by_sub_category_id(db: AsyncSession, sub_category_id: int) -> list[NoonProduct]:
        result = await db.execute(select(NoonProduct).where(NoonProduct.subCategoryId == sub_category_id))
        return result.scalars().all()

    @staticmethod
    async def get_by_brand_id(db: AsyncSession, brand_id: str) -> list[NoonProduct]:
        result = await db.execute(select(NoonProduct).where(NoonProduct.brandId == brand_id))
        return result.scalars().all()

    @staticmethod
    async def get_by_merchant(db: AsyncSession, merchant_name: str) -> list[NoonProduct]:
        result = await db.execute(select(NoonProduct).where(NoonProduct.merchant_name == merchant_name))
        return result.scalars().all()

    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[NoonProduct]:
        result = await db.execute(select(NoonProduct).offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def update(db: AsyncSession, record_id: int, **kwargs) -> Optional[NoonProduct]:
        record = await NoonProductController.get_by_id(db, record_id)
        if record is None:
            return None

        for key, value in kwargs.items():
            if hasattr(record, key) and value is not None:
                setattr(record, key, value)

        try:
            await db.commit()
            await db.refresh(record)
            return record
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to update NoonProduct {record_id}: {exc}") from exc

    @staticmethod
    async def delete(db: AsyncSession, record_id: int) -> bool:
        record = await NoonProductController.get_by_id(db, record_id)
        if record is None:
            return False

        try:
            await db.delete(record)
            await db.commit()
            return True
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonProduct {record_id}: {exc}") from exc

    @staticmethod
    async def delete_by_category_id(db: AsyncSession, category_id: int) -> int:
        records = await NoonProductController.get_by_category_id(db, category_id)
        if not records:
            return 0

        try:
            for record in records:
                await db.delete(record)
            await db.commit()
            return len(records)
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonProducts for category {category_id}: {exc}") from exc

    @staticmethod
    async def delete_by_brand_id(db: AsyncSession, brand_id: str) -> int:
        records = await NoonProductController.get_by_brand_id(db, brand_id)
        if not records:
            return 0

        try:
            for record in records:
                await db.delete(record)
            await db.commit()
            return len(records)
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonProducts for brand {brand_id}: {exc}") from exc