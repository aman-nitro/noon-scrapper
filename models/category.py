from models.base import Base
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Text,
    func,
)


class NoonCategory(Base):
    __tablename__ = "noon_category"

    id = Column(Integer, primary_key=True, index=True)
    categoryId = Column(Integer,nullable=False)
    categoryName = Column(Text,nullable=False)

    subCategoryId = Column(Integer,nullable=False)
    subCategoryName = Column(Text,nullable=False)

    createdAt = Column(DateTime,nullable=False,server_default=func.now())

    def __repr__(self):
        return (
            f"<NoonCategory("
            f"categoryId={self.categoryId}, "
            f"subCategoryId={self.subCategoryId}, "
            f"categoryName={self.categoryName}, "
            f"subCategoryName={self.subCategoryName}"
            f")>"
        )