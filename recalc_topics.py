import asyncio
import json
import logging
from database import Database
from classifier import ProjectClassifier

# Настройка логирования (чтобы видеть прогресс)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def apply_batch_update(db, updates):
    """
    Массовое обновление тегов для одной пачки проектов.
    updates: список кортежей [(external_id, topics_json), ...]
    """
    if not updates:
        return

    ids = [str(u[0]) for u in updates]  # external_id как int
    # Превращаем JSON-строки обратно в объекты Python, чтобы asyncpg понял jsonb[]
    topics_python = [json.loads(u[1]) for u in updates]

    query = """
        UPDATE projects AS p
        SET topics = t.topics_json::jsonb
        FROM (
            SELECT 
                unnest($1::int[]) AS external_id,
                unnest($2::jsonb[]) AS topics_json
        ) AS t
        WHERE p.external_id = t.external_id
    """
    
    async with db.pool.acquire() as conn:
        await conn.execute(query, ids, topics_python)


async def recalc_topics_paginated(db, batch_size=5000):
    """
    Пересчитывает классификацию для всех проектов пачками.
    batch_size — сколько проектов обрабатывать за один раз.
    """
    logger.info("🚀 Запуск пересчета классификации с пагинацией...")
    
    last_id = 0          # Курсор для пагинации (external_id > last_id)
    total_processed = 0
    total_projects = 0

    # 1. Сначала узнаем общее количество, чтобы понимать прогресс
    async with db.pool.acquire() as conn:
        total_projects = await conn.fetchval("SELECT COUNT(*) FROM projects")
    logger.info(f"📊 Всего проектов в БД: {total_projects}")

    if total_projects == 0:
        logger.info("❌ Проектов нет. Завершаем.")
        return

    while True:
        # 2. Забираем очередную пачку проектов (сортировка по external_id)
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    external_id as id,
                    title,
                    department
                FROM projects
                WHERE external_id > $1
                ORDER BY external_id ASC
                LIMIT $2
            """, last_id, batch_size)
            
            if not rows:
                logger.info("✅ Достигнут конец таблицы.")
                break

        # 3. Классифицируем каждый проект в пачке
        updates = []
        for row in rows:
            project = dict(row)
            title = project.get('title', '')
            # department у нас хранится как строка (VARCHAR)
            dept = project.get('department', '') or ''
            
            # Вызываем классификатор
            new_topics = ProjectClassifier.classify(title, dept)
            # Если классификатор вернул список, превращаем в JSON-строку
            topics_json = json.dumps(new_topics, ensure_ascii=False)
            updates.append((project['id'], topics_json))

        # 4. Обновляем пачку одним массовым запросом
        if updates:
            await apply_batch_update(db, updates)

        # 5. Сдвигаем курсор на последний обработанный ID
        last_id = rows[-1]['id']
        total_processed += len(rows)
        
        progress = (total_processed / total_projects) * 100
        logger.info(f"   ✅ Обработано {total_processed} из {total_projects} ({progress:.1f}%), last_id={last_id}")

        # Если пачка меньше запрошенного размера — значит, это последняя страница
        if len(rows) < batch_size:
            logger.info("🏁 Обработана последняя пачка.")
            break

    logger.info(f"🎯 ГОТОВО! Всего пересчитано проектов: {total_processed}")


async def main():
    db = Database()
    try:
        await db.connect()
        await recalc_topics_paginated(db, batch_size=5000)  
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await db.close()
        logger.info("🔌 Соединение с БД закрыто.")


if __name__ == "__main__":
    asyncio.run(main())