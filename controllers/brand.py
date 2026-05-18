from sqlalchemy.orm import Session
from models.brand import NoonBrand


class NoonBrandService:

    @staticmethod
    def create(db: Session, name: str):
        brand = NoonBrand(name=name)

        db.add(brand)
        db.commit()
        db.refresh(brand)

        return brand

    @staticmethod
    def get_by_id(db: Session, brand_id: int):
        return db.query(NoonBrand).filter(NoonBrand.id == brand_id).first()

    @staticmethod
    def get_all(db: Session):
        return db.query(NoonBrand).all()

    @staticmethod
    def update(db: Session, brand_id: int, name: str):
        brand = db.query(NoonBrand).filter(NoonBrand.id == brand_id).first()

        if not brand:
            return None

        brand.name = name
        db.commit()
        db.refresh(brand)

        return brand

    @staticmethod
    def delete(db: Session, brand_id: int):
        brand = db.query(NoonBrand).filter(NoonBrand.id == brand_id).first()

        if not brand:
            return False

        db.delete(brand)
        db.commit()

        return True