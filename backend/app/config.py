# backend/app/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Настройки Modbus-TCP
    MODBUS_HOST: str = "192.168.0.100"    # IP-адрес прибора (или эмулятора)
    MODBUS_PORT: int = 502                # Порт Modbus-TCP (обычно 502)
    MODBUS_UNIT_ID: int = 1               # Номер «Unit ID» (или Slave ID) на устройстве
    MODBUS_START_ADDR: int = 0            # Первый адрес регистра, с которого начинаем читать
    MODBUS_COUNT: int = 10                # Сколько регистров подряд читать

    # Интервал опроса (в секундах)
    POLL_INTERVAL: int = 1                # Каждые 1 секунду опрашивать устройство

    # Строка подключения к SQLite (асинхронный драйвер)
    DATABASE_URL: str = "sqlite+aiosqlite:///./modbus_cache.db"

    # Настройки FastAPI (на каких хосте/порте запускать)
    API_HOST: str = "0.0.0.0"              # 0.0.0.0 означает «слушать все интерфейсы»
    API_PORT: int = 8000                  # Порт, на котором будет работать HTTP-сервер

    # Список разрешённых адресов (CORS) для фронтенда (React на порту 5173)
    FRONTEND_URLS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ]


# Создаём один экземпляр настроек, чтобы можно было импортировать везде:
settings = Settings()
