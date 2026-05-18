from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.brand import NoonBrand


class NoonBrandService:

    @staticmethod
    async def create(db: AsyncSession, name: str):
        brand = NoonBrand(name=name)

        db.add(brand)
        await db.commit()
        await db.refresh(brand)
        return brand

    @staticmethod
    async def get_by_id(db: AsyncSession, brand_id: int):
        result = await db.execute(
            select(NoonBrand).where(NoonBrand.id == brand_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(db: AsyncSession):
        result = await db.execute(select(NoonBrand))
        return result.scalars().all()

    @staticmethod
    async def update(db: AsyncSession, brand_id: int, name: str):
        result = await db.execute(
            select(NoonBrand).where(NoonBrand.id == brand_id)
        )
        brand = result.scalar_one_or_none()

        if not brand:
            return None

        brand.name = name
        await db.commit()
        await db.refresh(brand)

        return brand

    @staticmethod
    async def delete(db: AsyncSession, brand_id: int):
        result = await db.execute(
            select(NoonBrand).where(NoonBrand.id == brand_id)
        )
        brand = result.scalar_one_or_none()

        if not brand:
            return False

        await db.delete(brand)
        await db.commit()

        return True