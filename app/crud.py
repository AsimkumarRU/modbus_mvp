# backend/app/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from .models import LatestValues
from typing import Optional


async def create_snapshot(db: AsyncSession, registers_list: list[int]) -> LatestValues:
    """
    Сохранить новый срез регистров в базу.
    :param db: асинхронная сессия SQLAlchemy (AsyncSession)
    :param registers_list: список чисел, например [123, 456, 789, ...]
    :return: созданный объект LatestValues
    """
    snapshot = LatestValues(registers=registers_list)
    db.add(snapshot)               # готовим к вставке в базу
    await db.commit()              # сохраняем изменения (вставляем строку)
    await db.refresh(snapshot)     # обновляем объект из БД, чтобы получить её поля (например, timestamp, id)
    return snapshot


async def read_latest_snapshot(db: AsyncSession) -> Optional[LatestValues]:
    """
    Получить самую свежую запись (по timestamp).
    :param db: асинхронная сессия SQLAlchemy
    :return: объект LatestValues или None, если таблица пуста
    """
    # Строим запрос: SELECT * FROM latest_values ORDER BY timestamp DESC LIMIT 1
    result = await db.execute(
        select(LatestValues).order_by(desc(LatestValues.timestamp)).limit(1)
    )
    # result.scalars().first() вернёт либо объект LatestValues, либо None
    return result.scalars().first()
