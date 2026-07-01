# worker.py
import asyncio
import logging
import sys
from database import Database
from updater import update_new_projects

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    
    logger.info("Запуск воркера обновления архива")
    db = Database()
    try:
        await db.connect()
        await update_new_projects(db, days_back=2)
        logger.info("Обновление успешно завершено")
    except Exception as e:
        logger.exception(f"Ошибка во время обновления: {e}")
        sys.exit(1)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())