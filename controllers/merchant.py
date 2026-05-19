from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from models.merchant import NoonMerchant


class NoonMerchantController:

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> NoonMerchant:
        record = NoonMerchant(**kwargs)
        try:
            db.add(record)
            # await db.commit()
            # await db.refresh(record)
            return record
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to create NoonMerchant: {exc}") from exc

    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int) -> Optional[NoonMerchant]:
        result = await db.execute(select(NoonMerchant).where(NoonMerchant.id == record_id))
        return result.scalars().first()

    @staticmethod
    async def get_by_name(db: AsyncSession, name: str) -> Optional[NoonMerchant]:
        result = await db.execute(select(NoonMerchant).where(NoonMerchant.name == name))
        return result.scalars().first()

    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[NoonMerchant]:
        result = await db.execute(select(NoonMerchant).offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def update(db: AsyncSession, record_id: int, **kwargs) -> Optional[NoonMerchant]:
        record = await NoonMerchantController.get_by_id(db, record_id)
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
            raise RuntimeError(f"Failed to update NoonMerchant {record_id}: {exc}") from exc

    @staticmethod
    async def delete(db: AsyncSession, record_id: int) -> bool:
        record = await NoonMerchantController.get_by_id(db, record_id)
        if record is None:
            return False

        try:
            await db.delete(record)
            await db.commit()
            return True
        except SQLAlchemyError as exc:
            await db.rollback()
            raise RuntimeError(f"Failed to delete NoonMerchant {record_id}: {exc}") from exc