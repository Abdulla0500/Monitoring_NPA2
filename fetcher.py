import asyncio
import aiohttp
import math
import logging
import time
from classifier import ProjectClassifier
logger = logging.getLogger(__name__)

def format_stages_json(stages_data):

        if not stages_data:
            return ""
        import json
        return json.dumps(stages_data, ensure_ascii=False)
class RegulationAPI:
    def __init__(self):
        self.base_url = "https://regulation.gov.ru"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://regulation.gov.ru',
            'Referer': 'https://regulation.gov.ru/',
            'Connection': 'keep-alive'
        }

    async def fetch_projects(self, session, page=1, pageSize=20,retries=3):
        url = f"{self.base_url}/api/public/PublicProjects/GetFiltered"

        payload = {
            "listParams": {
                "filterModel": {
                    "filters": "",
                    "page": page,
                    "pageSize": pageSize
                }
            },
            "orderedFields": [
                "title", "developedDepartment", "projectId", "projectType",
                "creationDate", "publicationDate", "stage", "status", "procedure"
            ]
        }

        for attempt in range(1, retries + 1):
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        projects = data.get('result', [])
                        total_count = data.get('totalCount', 0)
                        return projects, total_count

                    else:
                        print(f"⚠️ Страница {page}: статус {response.status}")

            except Exception as e:
                print(f"❌ Страница {page}, попытка {attempt}: {e}")

            if attempt < retries:
                await asyncio.sleep(1 * attempt)  

        print(f" Страница {page} не загрузилась после {retries} попыток")
        return [], 0
    async def _fetch_projects_filtered(self, session, page=1, pageSize=20, 
                                       start_date=None, end_date=None, retries=3):
        """Внутренний метод с фильтрацией (используется только для дат)"""
        url = f"{self.base_url}/api/public/PublicProjects/GetFiltered"
        
        payload = {
            "listParams": {
                "filterModel": {
                    "filters": "",
                    "page": page,
                    "pageSize": pageSize
                }
            },
            "orderedFields": [
                "title", "developedDepartment", "projectId", "projectType",
                "creationDate", "publicationDate", "stage", "status", "procedure"
            ]
        }
        
        # Добавляем фильтр только если указаны даты
        if start_date or end_date:
            date_filter = {
                "field": "publicationDate",
                "type": "dateRange",
                "value": {}
            }
            
            if start_date:
                date_filter["value"]["start"] = start_date
            if end_date:
                date_filter["value"]["end"] = end_date
                
            payload["listParams"]["filterModel"]["filters"] = date_filter
        
        # Остальной код такой же как в fetch_projects
        for attempt in range(1, retries + 1):
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        projects = data.get('result', [])
                        total_count = data.get('totalCount', 0)
                        return projects, total_count
                    else:
                        print(f"⚠️ Страница {page}: статус {response.status}")
            except Exception as e:
                print(f"❌ Страница {page}, попытка {attempt}: {e}")
            
            if attempt < retries:
                await asyncio.sleep(1 * attempt)
        
        print(f"❌ Страница {page} не загрузилась после {retries} попыток")
        return [], 0
    async def fetch_all_projects_optimized(self, max_pages=500, page_size=20, max_concurrent=20):
        print("=" * 70)
        print("🚀 ОПТИМИЗИРОВАННАЯ АСИНХРОННАЯ ЗАГРУЗКА")
        print("=" * 70)
        
        start_load = time.time()
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            first_projects, total_count = await self.fetch_projects(session, page=1, pageSize=page_size)
            
            if not first_projects:
                print("❌ Не удалось получить первую страницу")
                return []
            
            total_pages = math.ceil(total_count / page_size)

            if max_pages is None:
                pages_to_load = total_pages
            else:
                pages_to_load = min(max_pages, total_pages)

            print(f"📊 Всего проектов: {total_count}")
            print(f"📄 Всего страниц: {total_pages}")
            print(f"📥 Загружаем {pages_to_load} страниц по {max_concurrent} параллельно\n")
            
            all_projects = first_projects.copy()
            
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def fetch_page(page_num):
                async with semaphore:
                    projects, _ = await self.fetch_projects(session, page=page_num, pageSize=page_size)
                    if projects:
                        print(f"   ✅ Страница {page_num}: {len(projects)} проектов")
                    return projects
            
            tasks = [fetch_page(page) for page in range(2, pages_to_load + 1)]
            
            results = await asyncio.gather(*tasks)
            
            for projects in results:
                if projects:
                    all_projects.extend(projects)
            
            load_time = time.time() - start_load
            print(f"\n⏱ Время загрузки: {load_time:.2f} секунд")
            
            unique = {p['id']: p for p in all_projects}.values()
            projects_list = list(unique)
            
            for p in projects_list:
                title = p.get('title', '')
                dept = p.get('developedDepartment')
                if isinstance(dept, dict):
                    dept = dept.get('description', '')
                else:
                    dept = dept or ''
                topics = ProjectClassifier.classify(title, dept)
                p['classified_topics'] = topics
    
            print(f"🎯 ИТОГО ЗАГРУЖЕНО: {len(projects_list)} ПРОЕКТОВ (классифицировано)")
            return projects_list
        
    async def fetch_project_stages(self, project_id: str, session: aiohttp.ClientSession = None):
        close_session = False
        if session is None:
            session = aiohttp.ClientSession(headers=self.headers)
            close_session = True

        url = f"{self.base_url}/api/public/PublicProjects/GetProjectStages/{project_id}"
        try:
            logger.info(f"Запрос этапов для проекта {project_id}")
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения этапов проекта {project_id}: {e}")
            return None
        finally:
            if close_session:
                await session.close()
    async def fetch_new_projects(self, days_back=2, page_size=20, max_concurrent=20):
        from datetime import datetime, timedelta
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_back)
        
        return await self.fetch_projects_by_date_range(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            page_size=page_size,
            max_concurrent=max_concurrent
        )
    async def fetch_projects_by_date_range(self, start_date, end_date, page_size=20, max_concurrent=20):
        print("=" * 70)
        print(f"ЗАГРУЗКА ПРОЕКТОВ ЗА ПЕРИОД: {start_date} - {end_date}")
        print("=" * 70)
        start_load=time.time()

        async with aiohttp.ClientSession(headers=self.headers) as session:
            first_projects, total_count = await self._fetch_projects_filtered(
                session, 
                page=1, 
                pageSize=page_size,
                start_date=start_date,  
                end_date=end_date
            )
            if not first_projects:
                print("❌ Нет новых проектов за указанный период")
                return []
            
            total_pages = math.ceil(total_count / page_size)
            print(f"📊 Найдено проектов: {total_count}")
            print(f"📄 Страниц: {total_pages}")
            
            all_projects = first_projects.copy()
            
            semaphore = asyncio.Semaphore(max_concurrent)
            async def fetch_page(page_num):
                async with semaphore:
                    projects, _ = await self.fetch_projects(
                        session, 
                        page=page_num, 
                        pageSize=page_size,
                        start_date=start_date,
                        end_date=end_date
                    )
                    if projects:
                        print(f"   ✅ Страница {page_num}: {len(projects)} проектов")
                    return projects
            if total_pages > 1:
                tasks = [fetch_page(page) for page in range(2, total_pages + 1)]
                results = await asyncio.gather(*tasks)
                
                for projects in results:
                    if projects:
                        all_projects.extend(projects)
            
            load_time = time.time() - start_load
            print(f"\n⏱ Время загрузки: {load_time:.2f} секунд")
            print(f"🎯 ЗАГРУЖЕНО: {len(all_projects)} ПРОЕКТОВ")
            
            # Классифицируем проекты
            for p in all_projects:
                title = p.get('title', '')
                dept = p.get('developedDepartment')
                if isinstance(dept, dict):
                    dept = dept.get('description', '')
                else:
                    dept = dept or ''
                topics = ProjectClassifier.classify(title, dept)
                p['classified_topics'] = topics
            
            return all_projects
async def main():

    api = RegulationAPI()
    
    projects = await api.fetch_all_projects_optimized(max_pages=800, page_size=20, max_concurrent=20)

    
    SELECTED_TOPIC = 'ep'
    
    filtered_projects = [
    p for p in projects
    if 'ep' in ProjectClassifier.classify(
        p.get('title', ''),
        p.get('developedDepartment', {}).get('description', '')
        if isinstance(p.get('developedDepartment'), dict)
        else p.get('developedDepartment', '')
    )
    ]
    
    # Выводим только отфильтрованные проекты
    print(f"\n🔍 ПРОЕКТЫ ПО ТЕМЕ: {SELECTED_TOPIC}")
    print("=" * 70)
    print(f"Найдено проектов: {len(filtered_projects)}")
    print("=" * 70)
    
    for i, project in enumerate(filtered_projects[:80], 1):
        print(f"\n{i}. {project.get('title', 'Нет названия')[:100]}")
        print(f"   ID: {project.get('id', 'Нет ID')}")
        print(f"   Статус: {project.get('status', 'Нет статуса')}")
        print(f"   Стадия: {project.get('stage', 'Нет стадии')}")
        
        developer = project.get('developedDepartment', 'Не указан')
        if isinstance(developer, dict):
            developer = developer.get('description', 'Не указан')
        print(f"   Разработчик: {developer}")
        
        creation_date = project.get('creationDate', 'Не указана')
        if creation_date and len(creation_date) > 10:
            creation_date = creation_date[:10]
        print(f"   Дата создания: {creation_date}")
        print("-" * 50)



if __name__ == "__main__":
    asyncio.run(main())