# backend/app/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
import logging

from .models import LatestValues
from typing import Optional, List

logger = logging.getLogger(__name__)


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
    logger.info("Snapshot created with id %s", snapshot.id)
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
    snapshot = result.scalars().first()
    if snapshot:
        logger.debug("Fetched latest snapshot id %s", snapshot.id)
    else:
        logger.debug("No snapshots found in database")
    return snapshot


async def read_snapshot_history(db: AsyncSession, limit: int) -> List[LatestValues]:
    """Return last ``limit`` snapshots ordered by timestamp desc."""
    result = await db.execute(
        select(LatestValues).order_by(desc(LatestValues.timestamp)).limit(limit)
    )
    snapshots = result.scalars().all()
    logger.info("Fetched %s snapshots from history", len(snapshots))
    return snapshots
