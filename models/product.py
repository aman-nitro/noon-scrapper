from models.base import Base

from datetime import datetime
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

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    brandId = Column(Text, nullable=False)

    sku = Column(Text, nullable=False)
    product_url = Column(Text, nullable=True)
    imageUrl = Column(Text, nullable=True)

    price = Column(Integer, nullable=False)
    inventory = Column(Text, nullable=False)
    categoryId = Column(Integer, nullable=False)
    subCategoryId = Column(Integer, nullable=False)
    merchant_name = Column(Text, nullable=False)
    
    createdAt = Column(DateTime,nullable=False,server_default=func.now())
    updatedAt = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return (
            f"<BlinkitProduct("
            f"id={self.id}, "
            f"name={self.name}, "
            f"brandId={self.brandId}"
            f")>"
        )