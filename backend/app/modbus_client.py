# backend/app/modbus_client.py

import asyncio
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .config import settings
from typing import Optional, List

from .crud import create_snapshot
from .database import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession


async def read_registers() -> Optional[List[int]]:
    """
    Попытаться соединиться с Modbus-TCP устройством и прочитать holding registers.
    :return: список int значений регистров или None, если не удалось.
    """
    client = AsyncModbusTcpClient(host=settings.MODBUS_HOST, port=settings.MODBUS_PORT)

    try:
        connected = await client.connect()
        if not connected:
            return None

        rr = await client.read_holding_registers(
            address=settings.MODBUS_START_ADDR,
            count=settings.MODBUS_COUNT,
            slave=settings.MODBUS_UNIT_ID,  # <= правильный параметр!
        )

        if rr.isError():
            return None

        return rr.registers

    except ModbusException:
        return None

    finally:
        if client:
            client.close()

async def modbus_polling_task():
    while True:
        try:
            regs = await asyncio.wait_for(read_registers(), timeout=5.0)
            if regs:
                async with get_async_session() as session:
                    await create_snapshot(session, regs)
        except asyncio.TimeoutError:
            print("⏱️ Modbus polling timed out")
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
        await asyncio.sleep(5)
