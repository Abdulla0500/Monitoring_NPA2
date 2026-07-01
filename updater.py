# updater.py
import asyncio
import aiohttp
import logging
from fetcher import RegulationAPI, format_stages_json
from database import Database
from datetime import datetime

logger = logging.getLogger(__name__)

async def update_new_projects(db: Database, days_back: int = 2):
    api = RegulationAPI()
    
    logger.info("=" * 70)
    logger.info("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО ОБНОВЛЕНИЯ")
    logger.info("=" * 70)
    
    start_time = datetime.now()
    
    logger.info(f"📅 Загружаем проекты за последние {days_back} дней...")
    projects = await api.fetch_new_projects(
        days_back=days_back,
        page_size=20,
        max_concurrent=20
    )
    
    if not projects:
        logger.info("✅ Нет новых проектов для обновления")
        return
    
    logger.info(f"📊 Загружено {len(projects)} проектов из API")
    
    async with aiohttp.ClientSession(headers=api.headers) as session:
        semaphore = asyncio.Semaphore(10)
        
        async def process_project(proj):
            async with semaphore:
                proj_id = proj['id']
                
                existing = await db.get_project_by_external_id(proj_id)
                
                
                need_stages_update = False
                
                if not existing:
                    need_stages_update = True
                    logger.info(f"Новый проект: {proj.get('title', '')[:50]}...")
                else:
                    proj_date_raw = proj.get('publicationDate')
                    proj_date = datetime.fromisoformat(proj_date_raw) if proj_date_raw else None
                    
                    if existing.get('publication_date') != proj_date:
                        need_stages_update = True
                        logger.info(f"Изменилась дата публикации: {proj_id}")
                    elif existing.get('stage') != proj.get('stage'):
                        need_stages_update = True
                        logger.info(f"Изменилась стадия: {proj_id}")
                    elif existing.get('status') != proj.get('status'):
                        need_stages_update = True
                        logger.info(f"Изменился статус: {proj_id}")
                
                stages_str = ""
                if need_stages_update:
                    logger.info(f"Загружаем этапы для проекта {proj_id}")
                    stages_json = await api.fetch_project_stages(session, proj_id)
                    stages_str = format_stages_json(stages_json) if stages_json else ""
                else:
                    stages_str = existing.get('stages_info', "") if existing else ""
                    logger.debug(f"Пропускаем этапы для {proj_id} (без изменений)")

                project_data = {
                    'external_id': proj_id,
                    'title': proj.get('title', ''),
                    'department': proj.get('developedDepartment', {}).get('description', ''),
                    'creation_date': proj.get('creationDate'),
                    'publication_date': proj.get('publicationDate'),
                    'stage': proj.get('stage'),
                    'status': proj.get('status'),
                    'project_type_name': proj.get('projectType', {}).get('description', ''),
                    'procedure_name': proj.get('procedure', {}).get('description', ''),
                    'raw_json': proj,
                    'topics': proj.get('classified_topics', []),
                    'stages_info': stages_str,
                }
                
                await db.upsert_project(project_data)
                logger.debug(f"✅ Сохранен проект {proj_id}")
        
        tasks = [process_project(p) for p in projects]
        await asyncio.gather(*tasks)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 70)
    logger.info(f"✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО ЗА {elapsed:.2f} СЕКУНД")
    logger.info(f"📊 Обработано проектов: {len(projects)}")
    logger.info("=" * 70)


async def update_all_projects_and_stages(db: Database):
    api = RegulationAPI()
    
    logger.info("=" * 70)
    logger.info("🔄 ЗАПУСК ПОЛНОГО ОБНОВЛЕНИЯ (ВСЕ ПРОЕКТЫ)")
    logger.info("=" * 70)
    
    start_time = datetime.now()
    
    logger.info("Начинаем загрузку всех проектов...")
    projects = await api.fetch_all_projects_optimized(
        max_pages=None, 
        page_size=20, 
        max_concurrent=20
    )
    
    if not projects:
        logger.error("❌ Не удалось загрузить проекты")
        return
    
    logger.info(f"📊 Загружено {len(projects)} проектов из API")
    
    async with aiohttp.ClientSession(headers=api.headers) as session:
        semaphore = asyncio.Semaphore(10)
        
        async def process_project(proj):
            async with semaphore:
                proj_id = proj['id']
                
                logger.info(f"📥 Загружаем этапы для проекта {proj_id}")
                stages_json = await api.fetch_project_stages(session, proj_id)
                stages_str = format_stages_json(stages_json) if stages_json else ""
                
                project_data = {
                    'external_id': proj_id,
                    'title': proj.get('title', ''),
                    'department': proj.get('developedDepartment', {}).get('description', ''),
                    'creation_date': proj.get('creationDate'),
                    'publication_date': proj.get('publicationDate'),
                    'stage': proj.get('stage'),
                    'status': proj.get('status'),
                    'project_type_name': proj.get('projectType', {}).get('description', ''),
                    'procedure_name': proj.get('procedure', {}).get('description', ''),
                    'raw_json': proj,
                    'topics': proj.get('classified_topics', []),
                    'stages_info': stages_str,
                }
                await db.upsert_project(project_data)
                logger.debug(f"✅ Сохранен проект {proj_id}")
        
        tasks = [process_project(p) for p in projects]
        await asyncio.gather(*tasks)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 70)
    logger.info(f"✅ ПОЛНОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО ЗА {elapsed:.2f} СЕКУНД")
    logger.info(f"📊 Обработано проектов: {len(projects)}")
    logger.info("=" * 70)