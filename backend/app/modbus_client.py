# backend/app/modbus_client.py

import asyncio
import logging
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .config import settings
from typing import Optional, List

from .crud import create_snapshot
from .database import get_async_session

logger = logging.getLogger(__name__)


async def read_registers() -> Optional[List[int]]:
    """
    Попытаться соединиться с Modbus-TCP устройством и прочитать holding registers.
    :return: список int значений регистров или None, если не удалось.
    """
    client = AsyncModbusTcpClient(host=settings.MODBUS_HOST, port=settings.MODBUS_PORT)

    try:
        connected = await client.connect()
        if not connected:
            logger.warning("Could not connect to Modbus device")
            return None

        rr = await client.read_holding_registers(
            address=settings.MODBUS_START_ADDR,
            count=settings.MODBUS_COUNT,
            slave=settings.MODBUS_UNIT_ID,  # <= правильный параметр!
        )

        if rr.isError():
            logger.error("Error reading registers: %s", rr)
            return None

        logger.debug("Read %s registers", len(rr.registers))
        return rr.registers

    except ModbusException as exc:
        logger.error("Modbus exception: %s", exc)
        return None

    finally:
        if client:
            client.close()

async def modbus_polling_task():
    logger.info("Background polling started")
    while True:
        try:
            regs = await asyncio.wait_for(read_registers(), timeout=5.0)
            if regs:
                async with get_async_session() as session:
                    await create_snapshot(session, regs)
                logger.debug("Polling result saved")
        except asyncio.TimeoutError:
            logger.warning("Modbus polling timed out")
        except Exception as e:
            logger.error("Polling error: %s", e)
        await asyncio.sleep(5)
