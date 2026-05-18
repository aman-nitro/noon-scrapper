from models.base import Base
from sqlalchemy import Column, DateTime, Text, func, Integer


class NoonBrand(Base):
    __tablename__ = "noon_brand"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text,nullable=False)
    createdAt = Column(DateTime,nullable=False,server_default=func.now())
    updatedAt = Column(DateTime,nullable=False)

    def __repr__(self):
        return (
            f"<NoonBrand("
            f"id={self.id}, "
            f"name={self.name}"
            f")>"
        )