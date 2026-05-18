from models.base import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Text, func, Integer

class NoonBrand(Base):
    __tablename__ = "noon_brand"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)

    createdAt = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow
    )

    updatedAt = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )