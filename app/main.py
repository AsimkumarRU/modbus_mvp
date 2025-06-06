# backend/app/main.py

import asyncio
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Base
from .crud import create_snapshot, read_latest_snapshot
from .modbus_client import read_registers

# 1. Настраиваем SQLAlchemy Async Engine
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

# 2. Создаём фабрику сессий. class_=AsyncSession говорит: "сессии будут асинхронными"
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    latest = await read_latest_snapshot(db)
    if not latest:
        # Если таблица пуста, возвращаем ошибку 404
        raise HTTPException(status_code=404, detail="Нет данных в кеше")
    return {
        "timestamp": latest.timestamp,
        "registers": latest.registers,
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


@app.get("/snapshot")
async def api_snapshot(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: GET /snapshot
    Возвращает последнее значение из базы данных.
    Аналогичен /read_latest.
    """
    latest = await read_latest_snapshot(db)
    if not latest:
        raise HTTPException(status_code=404, detail="Нет данных в кеше")
    return {
        "timestamp": latest.timestamp,
        "registers": latest.registers,
    }


@app.post("/poll")
async def api_poll(db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт: POST /poll
    Выполняет ручной опрос устройства по Modbus и сохраняет результат.
    """
    regs = await read_registers()
    if regs is None:
        raise HTTPException(status_code=503, detail="Не удалось опросить устройство")
    snapshot = await create_snapshot(db, regs)
    return {
        "timestamp": snapshot.timestamp,
        "registers": snapshot.registers,
    }


async def modbus_polling_task():
    """
    Фоновая корутина, которая постоянно работает «в фоне».
    Каждые settings.POLL_INTERVAL секунд:
    - Пытается прочитать регистры с прибора (read_registers())
    - Если получилось, сохраняет их в базу (create_snapshot)
    - Если нет — молча игнорирует и ждёт следующей итерации
    """
    while True:
        # 1. Попытка «живого» опроса
        regs = await read_registers()

        # 2. Если получили список из регистров (не None), сохраняем в базу
        if regs is not None:
            async with async_session() as session:
                await create_snapshot(session, regs)

        # 3. Ждём заданный интервал (например, 5 секунд)
        await asyncio.sleep(settings.POLL_INTERVAL)
