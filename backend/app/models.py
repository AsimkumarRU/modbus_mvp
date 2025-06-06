# backend/app/models.py

from sqlalchemy import Column, Integer, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

# Создаём «базовый» класс, от которого будут наследоваться все модели (таблицы)
Base = declarative_base()


class LatestValues(Base):
    __tablename__ = "latest_values"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    registers = Column(JSON, nullable=False)
    # В столбце "registers" храним JSON-массив, например [123, 456, 789, ...].
