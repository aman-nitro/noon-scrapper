from models.base import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)


class NoonProduct(Base):
    __tablename__ = "noon_product"

    name = Column(Text, nullable=False)
    brandId = Column(
        Text,
        ForeignKey(
            "NoonBrand.id",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    unit = Column(Text, nullable=False)
    price = Column(Integer, nullable=False)
    categoryId = Column(Integer, nullable=False)
    subCategoryId = Column(Integer, nullable=False)

    createdAt = Column(DateTime,nullable=False,server_default=func.now())
    updatedAt = Column(DateTime,nullable=False)
    imageUrl = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<BlinkitProduct("
            f"id={self.id}, "
            f"name={self.name}, "
            f"brandId={self.brandId}"
            f")>"
        )