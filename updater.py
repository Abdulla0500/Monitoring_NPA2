# updater.py
import asyncio
import aiohttp
import logging
from fetcher import RegulationAPI, format_stages_json
from database import Database
from datetime import datetime

logger = logging.getLogger(__name__)

async def update_all_projects_and_stages(db: Database):
    api = RegulationAPI()
    
    logger.info("Начинаем загрузку списка проектов...")
    projects = await api.fetch_all_projects_optimized(max_pages=None, page_size=20, max_concurrent=20)
    if not projects:
        logger.error("Не удалось загрузить проекты")
        return
    logger.info(f"Загружено {len(projects)} проектов из API")
    
    async with aiohttp.ClientSession(headers=api.headers) as session:
        semaphore = asyncio.Semaphore(10)  # ограничиваем параллельные запросы
        
        async def process_project(proj):
            async with semaphore:
                proj_id = proj['id']
                existing = await db.get_project_by_external_id(proj_id)
                need_stages_update = False
                if not existing:
                    need_stages_update = True
                else:
                    proj_date_raw = proj.get('publicationDate')
                    proj_date = datetime.fromisoformat(proj_date_raw) if proj_date_raw else None

                    if existing['publication_date'] != proj_date:
                        need_stages_update = True
                    elif existing['stage'] != proj.get('stage'):
                        need_stages_update = True
                
                stages_str = ""
                if need_stages_update:
                    stages_json = await api.fetch_project_stages(session, proj_id)
                    stages_str = format_stages_json(stages_json) if stages_json else ""
                else:
                    stages_str = existing['stages_info'] if existing else ""
                
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
        
        tasks = [process_project(p) for p in projects]
        await asyncio.gather(*tasks)
    
    logger.info("Обновление архива и этапов завершено")