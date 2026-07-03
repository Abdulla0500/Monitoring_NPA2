import asyncio
import logging
from database import Database
from classifier import ProjectClassifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def apply_batch_update(db, updates):
    """Обновляет пачку проектов одним запросом"""
    if not updates:
        return
    ids = [u[0] for u in updates]
    topics_list = [u[1] for u in updates]  # каждый элемент — список тем
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
        await conn.execute(query, ids, topics_list)

async def recalc_topics_paginated(db, batch_size=5000):
    logger.info("🚀 Запуск пересчета классификации с пагинацией...")
    async with db.pool.acquire() as conn:
        total_projects = await conn.fetchval("SELECT COUNT(*) FROM projects")
    logger.info(f"📊 Всего проектов в БД: {total_projects}")
    if total_projects == 0:
        return

    last_id = 0
    total_processed = 0
    while True:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT external_id as id, title, department
                FROM projects
                WHERE external_id > $1
                ORDER BY external_id ASC
                LIMIT $2
            """, last_id, batch_size)
            if not rows:
                break

        updates = []
        for row in rows:
            title = row.get('title', '')
            dept = row.get('department', '') or ''
            new_topics = ProjectClassifier.classify(title, dept)
            # Защита от set (если классификатор вернул множество)
            if isinstance(new_topics, set):
                new_topics = list(new_topics)
            updates.append((row['id'], new_topics))

        if updates:
            await apply_batch_update(db, updates)

        last_id = rows[-1]['id']
        total_processed += len(rows)
        progress = (total_processed / total_projects) * 100
        logger.info(f"   ✅ Обработано {total_processed} из {total_projects} ({progress:.1f}%), last_id={last_id}")

        if len(rows) < batch_size:
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