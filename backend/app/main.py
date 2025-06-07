# backend/app/main.py

import asyncio
import logging
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Base
from .crud import create_snapshot, read_latest_snapshot, read_snapshot_history
from .modbus_client import read_registers, modbus_polling_task
from .database import engine, async_session

logging.basicConfig(
    filename=settings.LOG_FILE,
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 3. Создаём экземпляр FastAPI
app = FastAPI()

# 4. Настраиваем CORS, чтобы фронтенд (React на 5173) мог обращаться к API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """
    Эта функция будет вызвана автоматически при старте веб-сервера.
    Здесь мы:
    1. Создаём таблицы в базе (если ещё не созданы).
    2. Запускаем фоновую корутину modbus_polling_task().
    """
    # 1. Создаём таблицы: LatestValues (если их ещё нет)
    logger.info("Application startup: creating tables and starting polling task")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def safe_polling():
        try:
            await modbus_polling_task()
        except Exception as e:
            logger.error("Polling task crashed: %s", e)

    # 2. Запускаем фоновую задачу (без await, чтобы она работала в фоне)
    asyncio.create_task(modbus_polling_task())


async def get_db() -> AsyncSession:
    """
    Функция-зависимость для FastAPI: при каждом запросе
    она создаёт новую сессию (AsyncSession) и возвращает её.
    После ответа она автоматически закроет сессию.
    """
    async with async_session() as session:
        yield session


@app.get("/read_latest")
async def api_read_latest(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: GET /read_latest
    Возвращает последнее кешированное значение регистров.
    Если в базе нет ни одной записи, возвращает 404.
    """
    logger.info("/read_latest called")
    latest = await read_latest_snapshot(db)
    if not latest:
        # Если таблица пуста, возвращаем ошибку 404
        raise HTTPException(status_code=404, detail="Нет данных в кеше")
    return {
        "timestamp": latest.timestamp,
        "registers": latest.registers,
    }


# --- New endpoints -------------------------------------------------------


@app.get("/snapshot")
async def api_snapshot(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: GET /snapshot
    Возвращает последнюю сохранённую запись из базы. Если её нет, 404.
    """
    logger.info("/snapshot called")
    latest = await read_latest_snapshot(db)
    if not latest:
        raise HTTPException(status_code=404, detail="Нет данных в кеше")
    return {
        "timestamp": latest.timestamp,
        "registers": latest.registers,
    }


@app.get("/history")
async def api_history(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """Return last N snapshots from the database."""
    logger.info("/history called with limit %s", limit)
    snapshots = await read_snapshot_history(db, limit)
    return [
        {"timestamp": s.timestamp, "registers": s.registers}
        for s in snapshots
    ]


@app.post("/poll")
async def api_poll(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: POST /poll
    Выполняет единичный опрос Modbus-устройства и сохраняет результат в базу.
    Возвращает сохранённые данные. Если опрос не удался — 503.
    """
    logger.info("/poll called")
    regs = await read_registers()
    if regs is None:
        raise HTTPException(status_code=503, detail="Не удалось опросить устройство")
    snapshot = await create_snapshot(db, regs)
    return {
        "timestamp": snapshot.timestamp,
        "registers": snapshot.registers,
    }


@app.get("/read_live")
async def api_read_live(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: GET /read_live
    Пытается «живой» опрос: читает регистры напрямую с прибора.
    Если не удалось (регистры не прочитаны), возвращает последний кеш.
    Если и кеша нет — 503 (Service Unavailable).
    """
    # 1. Живой опрос Modbus
    logger.info("/read_live called")
    regs = await read_registers()
    if regs is None:
        # 2. Если «живой» опрос провалился, пытаемся вернуть кеш
        latest = await read_latest_snapshot(db)
        if not latest:
            # Если кеша тоже нет — возвращаем 503
            raise HTTPException(status_code=503, detail="Живой опрос не удался и кеш пуст")
        # Возвращаем кеш с заметкой
        return {
            "timestamp": latest.timestamp,
            "registers": latest.registers,
            "note": "Вернуто последнее значение из кеша"
        }

    # 3. Если живой опрос удался, возвращаем «чистые» данные (timestamp=None для обозначения „живых“)
    return {"timestamp": None, "registers": regs}


async def modbus_polling_task():
    """
    Фоновая корутина, которая постоянно работает «в фоне».
    Каждые settings.POLL_INTERVAL секунд:
    - Пытается прочитать регистры с прибора (read_registers())
    - Если получилось, сохраняет их в базу (create_snapshot)
    - Если нет — молча игнорирует и ждёт следующей итерации
    """
    logger.info("Starting Modbus polling task")
    while True:
        # 1. Попытка «живого» опроса
        regs = await read_registers()

        # 2. Если получили список из регистров (не None), сохраняем в базу
        if regs is not None:
            async with async_session() as session:
                await create_snapshot(session, regs)
            logger.debug("Saved polled registers to database")

        # 3. Ждём заданный интервал (например, 5 секунд)
        await asyncio.sleep(settings.POLL_INTERVAL)

@app.get("/")
async def root():
    logger.info("root endpoint called")
    return {"message": "FastAPI работает!"}
