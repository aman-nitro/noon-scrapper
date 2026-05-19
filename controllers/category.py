from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from models.category import NoonCategory


class NoonCategoryController:

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> NoonCategory:
        record = NoonCategory(**kwargs)
        try:
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return record
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to create NoonCategory: {exc}") from exc

    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int) -> Optional[NoonCategory]:
        result = await db.execute(select(NoonCategory).where(NoonCategory.id == record_id))
        return result.scalars().first()

    @staticmethod
    async def get_by_category_id(db: AsyncSession, category_id: int) -> list[NoonCategory]:
        result = await db.execute(select(NoonCategory).where(NoonCategory.categoryId == category_id))
        return result.scalars().all()

    @staticmethod
    async def get_by_sub_category_id(db: AsyncSession, sub_category_id: int) -> list[NoonCategory]:
        result = await db.execute(select(NoonCategory).where(NoonCategory.subCategoryId == sub_category_id))
        return result.scalars().all()

    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[NoonCategory]:
        result = await db.execute(select(NoonCategory).offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def update(db: AsyncSession, record_id: int, **kwargs) -> Optional[NoonCategory]:
        record = await NoonCategoryController.get_by_id(db, record_id)
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
            raise RuntimeError(f"Failed to update NoonCategory {record_id}: {exc}") from exc

    @staticmethod
    async def delete(db: AsyncSession, record_id: int) -> bool:
        record = await NoonCategoryController.get_by_id(db, record_id)
        if record is None:
            return False

        try:
            await db.delete(record)
            await db.commit()
            return True
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonCategory {record_id}: {exc}") from exc

    @staticmethod
    async def delete_by_category_id(db: AsyncSession, category_id: int) -> int:
        records = await NoonCategoryController.get_by_category_id(db, category_id)
        if not records:
            return 0

        try:
            for record in records:
                await db.delete(record)
            await db.commit()
            return len(records)
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonCategories for category {category_id}: {exc}") from exc