import asyncpg
import asyncio
from datetime import time, date
from config import config1
import json


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    # -------------------- ПОДКЛЮЧЕНИЕ --------------------
    async def connect(self):
        max_retries = 10

        for attempt in range(max_retries):
            try:
                self.pool = await asyncpg.create_pool(**config1.DB_CONFIG)
                print("✅ PostgreSQL подключен")
                return
            except Exception as e:
                print(f"Попытка {attempt + 1}/{max_retries}: ждем PostgreSQL...")
                await asyncio.sleep(3)

        raise Exception("❌ Не удалось подключиться к PostgreSQL")

    # -------------------- ТАБЛИЦЫ --------------------
    async def create_tables(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                username VARCHAR(255),
                department VARCHAR(255),
                role VARCHAR(50) DEFAULT 'analyst',
                notification_time TIME DEFAULT  '06:00',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                topic VARCHAR(255) NOT NULL,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, topic)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id SERIAL PRIMARY KEY,
                external_id INTEGER UNIQUE,
                title TEXT NOT NULL,
                department VARCHAR(255),
                creation_date TIMESTAMP,
                publication_date TIMESTAMP,
                stage VARCHAR(100),
                status VARCHAR(100),
                project_type_name VARCHAR(255),
                procedure_name VARCHAR(255),
                raw_json JSONB,
                topics JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS saved_projects (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, project_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS projects_title_fts_idx
            ON projects
            USING GIN (to_tsvector('russian', coalesce(title, '')));"""
        ]
        async with self.pool.acquire() as conn:
            for query in queries:
                await conn.execute(query)
            await conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS stages_info TEXT")


    async def add_user(self, telegram_id, first_name, last_name, username, role='analyst'):
        query = """
        INSERT INTO users (telegram_id, first_name, last_name, username, role, notification_time)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (telegram_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            username = EXCLUDED.username
        RETURNING user_id;
        """

        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                query,
                telegram_id,
                first_name,
                last_name,
                username,
                role,
                time(6, 0)
            )

    async def get_user_by_tg_id(self, telegram_id):
        query = "SELECT * FROM users WHERE telegram_id = $1"

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, telegram_id)

    # -------------------- ПОДПИСКИ --------------------
    async def add_subscription(self, user_id, topic):
        query = """
        INSERT INTO subscriptions (user_id, topic)
        VALUES ($1, $2)
        ON CONFLICT (user_id, topic) DO NOTHING;
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, topic)

    async def remove_subscription(self, user_id: int, topic: str):
        query = """
        DELETE FROM subscriptions 
        WHERE user_id = $1 AND topic = $2;
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, user_id, topic)
            # result выглядит как "DELETE 1" или "DELETE 0"
            return int(result.split()[-1]) > 0
        
    async def get_user_subscriptions(self, user_id):
        query = "SELECT topic FROM subscriptions WHERE user_id = $1"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return [r["topic"] for r in rows]

    # -------------------- ПРОЕКТЫ --------------------
    async def add_project(self, project_data: dict):
        raw_json = json.dumps(project_data.get("raw_json"))
        topics_json = json.dumps(project_data.get("topics"))
        query = """
        INSERT INTO projects (
            external_id, title, department, creation_date,
            publication_date, stage, status,
            project_type_name, procedure_name,
            raw_json, topics,stages_info
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12)
        ON CONFLICT (external_id) DO NOTHING;
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                project_data.get("external_id"),
                project_data.get("title"),
                project_data.get("department"),
                project_data.get("creation_date"),
                project_data.get("publication_date"),
                project_data.get("stage"),
                project_data.get("status"),
                project_data.get("project_type_name"),
                project_data.get("procedure_name"),
                raw_json,
                topics_json,
                project_data.get("stages_info", "")

            )
    async def get_all_projects(self):
        query = """
            SELECT 
                external_id as id,
                title,
                department,
                creation_date,
                publication_date,
                stage,
                status,
                project_type_name,
                procedure_name,
                topics,
                raw_json,
                stages_info
            FROM projects
            ORDER BY publication_date DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            projects = []
            for row in rows:
                # Преобразуем JSONB поля, если они пришли как строки
                topics_val = row['topics']
                if isinstance(topics_val, str):
                    topics_val = json.loads(topics_val)
                raw_json_val = row['raw_json']
                if isinstance(raw_json_val, str):
                    raw_json_val = json.loads(raw_json_val)
                project = {
                    'id': row['id'],
                    'title': row['title'],
                    'developedDepartment': {'description': row['department']} if row['department'] else None,
                    'creationDate': row['creation_date'].isoformat() if row['creation_date'] else None,
                    'publicationDate': row['publication_date'].isoformat() if row['publication_date'] else None,
                    'stage': row['stage'],
                    'status': row['status'],
                    'projectType': {'description': row['project_type_name']} if row['project_type_name'] else None,
                    'procedure': {'description': row['procedure_name']} if row['procedure_name'] else None,
                    'classified_topics': topics_val if topics_val else [],
                    'stages_info': row['stages_info'] or '',
                    'raw_json': raw_json_val
                }
                projects.append(project)
            return projects

    async def upsert_project(self, project_data: dict):
        raw_json = json.dumps(project_data.get("raw_json"))
        topics_json = json.dumps(project_data.get("topics"))
        query = """
        INSERT INTO projects (
            external_id, title, department, creation_date,
            publication_date, stage, status,
            project_type_name, procedure_name,
            raw_json, topics, stages_info
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12)
        ON CONFLICT (external_id) DO UPDATE SET
            title = EXCLUDED.title,
            department = EXCLUDED.department,
            creation_date = EXCLUDED.creation_date,
            publication_date = EXCLUDED.publication_date,
            stage = EXCLUDED.stage,
            status = EXCLUDED.status,
            project_type_name = EXCLUDED.project_type_name,
            procedure_name = EXCLUDED.procedure_name,
            raw_json = EXCLUDED.raw_json,
            topics = EXCLUDED.topics,
            stages_info = EXCLUDED.stages_info;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query,
                project_data.get("external_id"),
                project_data.get("title"),
                project_data.get("department"),
                project_data.get("creation_date"),
                project_data.get("publication_date"),
                project_data.get("stage"),
                project_data.get("status"),
                project_data.get("project_type_name"),
                project_data.get("procedure_name"),
                raw_json,
                topics_json,
                project_data.get("stages_info", ""),
            )

    async def get_project_by_external_id(self, external_id: int):
        query = """
        SELECT publication_date, stage, stages_info 
        FROM projects 
        WHERE external_id = $1
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, external_id)
    # -------------------- УВЕДОМЛЕНИЯ --------------------
    async def log_notification(self, user_id, project_id):
        query = """
        INSERT INTO notifications_log (user_id, project_id)
        VALUES ($1, $2)
        ON CONFLICT (user_id, project_id) DO NOTHING;
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, project_id)

    async def get_user_id(self, telegram_id: int) -> int | None:
        query = "SELECT user_id FROM users WHERE telegram_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, telegram_id)
    async def set_user_role(self,user_id, role):
        query="UPDATE users SET role = $1 WHERE user_id = $2"
        async with self.pool.acquire() as conn:
            return await conn.execute(query,role, user_id)     
    async def get_user_role(self, user_id: int) -> int | None:
        query = "SELECT role FROM users WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, user_id)  
    async def project_exists(self, external_id: int) -> bool:
        query = "SELECT 1 FROM projects WHERE external_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, external_id) is not None
        
    async def get_notification_time(self, telegram_id: int) -> str:
        query = 'SELECT notification_time FROM users WHERE telegram_id = $1'
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, telegram_id)
        if result and isinstance(result, time):
            return result.strftime('%H:%M')
        return '06:00'
    async def set_notification_time(self, telegram_id: int, time_str: str) -> bool:
        try:
            hours, minutes = map(int, time_str.split(':'))
            notification_time = time(hour=hours, minute=minutes)
        except (ValueError, AttributeError):
            return False

        query = "UPDATE users SET notification_time = $1 WHERE telegram_id = $2"
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, notification_time, telegram_id)
        return int(result.split()[1]) > 0

    async def get_users_by_notification_time(self, current_time_str: str):

        try:
            hours, minutes = map(int, current_time_str.split(':'))
            current_time_obj = time(hour=hours, minute=minutes)
        except (ValueError, AttributeError):
            return []
        query = """
            SELECT telegram_id, user_id, role
            FROM users
            WHERE notification_time = $1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, current_time_obj)
            return [dict(row) for row in rows]

    async def get_yesterday_projects_for_user(self, user_id: int):

        # 1. Получаем темы, на которые подписан пользователь
        subs_query = "SELECT topic FROM subscriptions WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            subs_rows = await conn.fetch(subs_query, user_id)
            if not subs_rows:
                return []
            topics = [row['topic'] for row in subs_rows]

        # 2. Запрос проектов за вчера, с фильтром по темам и исключением уже отправленных
        query = """
            SELECT 
                p.external_id as id,
                p.title,
                p.department,
                p.publication_date,
                p.creation_date,
                p.stage,
                p.status,
                p.project_type_name,
                p.procedure_name,
                p.raw_json,
                p.topics,
                p.stages_info
            FROM projects p
            WHERE 
                p.topics ?| $2                    -- пересечение тем
                AND DATE(COALESCE(p.publication_date, p.creation_date)) = CURRENT_DATE - INTERVAL '1 day'
                AND NOT EXISTS (
                    SELECT 1 FROM notifications_log nl
                    WHERE nl.user_id = $1 AND nl.project_id = p.project_id
                )
            ORDER BY p.publication_date DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, topics)


        projects = []
        for row in rows:
            # Обрабатываем topics (JSONB -> список)
            topics_val = row['topics']
            if isinstance(topics_val, str):
                import json
                topics_val = json.loads(topics_val)
            elif topics_val is None:
                topics_val = []

            # Обрабатываем raw_json (может быть None или строка JSON)
            raw = row['raw_json']
            if raw and isinstance(raw, str):
                import json
                raw = json.loads(raw)
            if not raw:
                raw = {}

            raw['id'] = row['id']
            raw['title'] = row['title']
            raw['developedDepartment'] = {'description': row['department']} if row['department'] else None
            raw['publicationDate'] = row['publication_date'].isoformat() if row['publication_date'] else None
            raw['creationDate'] = row['creation_date'].isoformat() if row['creation_date'] else None
            raw['stage'] = row['stage']
            raw['status'] = row['status']
            raw['projectType'] = {'description': row['project_type_name']} if row['project_type_name'] else None
            raw['procedure'] = {'description': row['procedure_name']} if row['procedure_name'] else None
            raw['classified_topics'] = topics_val
            raw['stages_info'] = row['stages_info'] or ''

            projects.append(raw)

        return projects
    async def get_projects_by_date(self, user_id: int, target_date):

        subs_query = "SELECT topic FROM subscriptions WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            subs_rows = await conn.fetch(subs_query, user_id)
            if not subs_rows:
                return []
            topics = [row['topic'] for row in subs_rows]

        query = """
            SELECT 
                p.external_id as id,
                p.title,
                p.department,
                p.publication_date,
                p.creation_date,
                p.stage,
                p.status,
                p.project_type_name,
                p.procedure_name,
                p.raw_json,
                p.topics,
                p.stages_info
            FROM projects p
            WHERE 
                p.topics ?| $2
                AND DATE(COALESCE(p.publication_date, p.creation_date)) = $3
                AND NOT EXISTS (
                    SELECT 1 FROM notifications_log nl
                    WHERE nl.user_id = $1 AND nl.project_id = p.project_id
                )
            ORDER BY p.publication_date DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, topics, target_date)

        # Преобразуем в тот же формат, что и в get_yesterday_projects_for_user
        projects = []
        for row in rows:
            topics_val = row['topics']
            if isinstance(topics_val, str):
                import json
                topics_val = json.loads(topics_val)
            elif topics_val is None:
                topics_val = []

            raw = row['raw_json']
            if raw and isinstance(raw, str):
                import json
                raw = json.loads(raw)
            if not raw:
                raw = {}

            raw['id'] = row['id']
            raw['title'] = row['title']
            raw['developedDepartment'] = {'description': row['department']} if row['department'] else None
            raw['publicationDate'] = row['publication_date'].isoformat() if row['publication_date'] else None
            raw['creationDate'] = row['creation_date'].isoformat() if row['creation_date'] else None
            raw['stage'] = row['stage']
            raw['status'] = row['status']
            raw['projectType'] = {'description': row['project_type_name']} if row['project_type_name'] else None
            raw['procedure'] = {'description': row['procedure_name']} if row['procedure_name'] else None
            raw['classified_topics'] = topics_val
            raw['stages_info'] = row['stages_info'] or ''

            projects.append(raw)
        return projects

    async def mark_notification_sent(self, user_id: int, project_external_id: int):
        # Сначала нужно найти project_id по external_id
        get_project_id_query = "SELECT project_id FROM projects WHERE external_id = $1"
        async with self.pool.acquire() as conn:
            project_id = await conn.fetchval(get_project_id_query, project_external_id)
            if not project_id:
                return False
            # Вставляем запись, игнорируя дубликаты
            insert_query = """
                INSERT INTO notifications_log (user_id, project_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, project_id) DO NOTHING
            """
            result = await conn.execute(insert_query, user_id, project_id)
            # Если вставлено, возвращаем True
            return result.endswith("1")  # "INSERT 0 1" -> True
    # database.py (добавить в конец класса Database)

    async def get_unique_developers(self) -> list:
        query = """
            SELECT DISTINCT department
            FROM projects
            WHERE department IS NOT NULL AND department != ''
            ORDER BY department
            LIMIT 500
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [row['department'] for row in rows]

    async def search_projects_with_filters(self, filters: dict, limit: int = 10000, offset: int = 0) -> list:

        conditions = []
        params = []
        param_index = 1

        if 'Разработчик' in filters:
            conditions.append(f"department ILIKE ${param_index}")
            params.append(f"%{filters['Разработчик']}%")
            param_index += 1

        if 'Этап' in filters:
            stage_val = filters['Этап']
            if stage_val == "Не определен":
                conditions.append("(stage IS NULL OR stage = '')")
            else:
                conditions.append(f"stage = ${param_index}")
                params.append(stage_val)
                param_index += 1

        if 'Процедура' in filters:
            conditions.append(f"procedure_name = ${param_index}")
            params.append(filters['Процедура'])
            param_index += 1

        if 'Статус' in filters:
            conditions.append(f"status = ${param_index}")
            params.append(filters['Статус'])
            param_index += 1
        
        if 'title' in filters:
            conditions.append(f"to_tsvector('russian', coalesce(title,'')) @@ plainto_tsquery('russian', ${param_index})")
            params.append(filters['title'])
            param_index += 1

        if 'publication_date_range' in filters:
            drange = filters['publication_date_range']
            start_date = drange.get('start')
            end_date = drange.get('end')
            if start_date and end_date:
                start_obj = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
                end_obj = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
                conditions.append(f"publication_date BETWEEN ${param_index} AND ${param_index+1}")
                params.append(start_obj)
                params.append(end_obj)
                param_index += 2
            elif start_date:
                start_obj = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
                conditions.append(f"publication_date >= ${param_index}")
                params.append(start_obj)
                param_index += 1
            elif end_date:
                end_obj = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
                conditions.append(f"publication_date <= ${param_index}")
                params.append(end_obj)
                param_index += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT 
                external_id as id,
                title,
                department,
                creation_date,
                publication_date,
                raw_json,
                topics,
                stages_info,
                stage,
                status,
                procedure_name
            FROM projects
            WHERE {where_clause}
            ORDER BY publication_date DESC NULLS LAST
            LIMIT ${param_index} OFFSET ${param_index+1}
        """
        params.append(limit)
        params.append(offset)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        projects = []
        for row in rows:
            raw_json = row['raw_json']
            if isinstance(raw_json, str):
                import json
                raw_json = json.loads(raw_json)
            topics_val = row['topics']
            if isinstance(topics_val, str):
                topics_val = json.loads(topics_val)
            project = {
                'id': row['id'],
                'title': row['title'],
                'developedDepartment': {'description': row['department']} if row['department'] else None,
                'creationDate': row['creation_date'].isoformat() if row['creation_date'] else None,
                'publicationDate': row['publication_date'].isoformat() if row['publication_date'] else None,
                'raw_json': raw_json,
                'classified_topics': topics_val if topics_val else [],
                'stages_info': row['stages_info'] or '',
                'stage': row['stage'],
                'status': row['status'],
                'procedure_name': row['procedure_name']
            }
            projects.append(project)
        return projects
    # database.py добавить методы в класс Database

    async def add_saved_project(self, user_id: int, external_id: int) -> bool:
        """Сохраняет проект в избранное пользователя. Возвращает True, если сохранение успешно."""
        # сначала находим project_id по external_id
        get_id_query = "SELECT project_id FROM projects WHERE external_id = $1"
        async with self.pool.acquire() as conn:
            project_id = await conn.fetchval(get_id_query, external_id)
            if not project_id:
                return False
            insert_query = """
                INSERT INTO saved_projects (user_id, project_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, project_id) DO NOTHING
            """
            result = await conn.execute(insert_query, user_id, project_id)
            return result.endswith("1")  # "INSERT 0 1"

    async def remove_saved_project(self, user_id: int, external_id: int) -> bool:
        """Удаляет проект из избранного. Возвращает True, если запись была удалена."""
        get_id_query = "SELECT project_id FROM projects WHERE external_id = $1"
        async with self.pool.acquire() as conn:
            project_id = await conn.fetchval(get_id_query, external_id)
            if not project_id:
                return False
            delete_query = "DELETE FROM saved_projects WHERE user_id = $1 AND project_id = $2"
            result = await conn.execute(delete_query, user_id, project_id)
            return int(result.split()[1]) > 0

    async def get_saved_projects(self, user_id: int) -> list:
        """Возвращает список проектов, сохранённых пользователем, в том же формате,
        что и search_projects_with_filters / get_all_projects."""
        query = """
            SELECT 
                p.external_id as id,
                p.title,
                p.department,
                p.publication_date,
                p.creation_date,
                p.stage,
                p.status,
                p.raw_json,
                p.topics,
                p.stages_info,
                p.project_type_name,
                p.procedure_name
            FROM saved_projects sp
            JOIN projects p ON sp.project_id = p.project_id
            WHERE sp.user_id = $1
            ORDER BY sp.saved_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        projects = []
        import json
        for row in rows:
            raw = row['raw_json']
            if isinstance(raw, str):
                raw = json.loads(raw)
            topics_val = row['topics']
            if isinstance(topics_val, str):
                topics_val = json.loads(topics_val)
            projects.append({
                'id': row['id'],
                'title': row['title'],
                'developedDepartment': {'description': row['department']} if row['department'] else None,
                'publicationDate': row['publication_date'].isoformat() if row['publication_date'] else None,
                'creationDate': row['creation_date'].isoformat() if row['creation_date'] else None,
                'stage': row['stage'],
                'status': row['status'],
                'project_type_name': row['project_type_name'],
                'procedure_name': row['procedure_name'],
                'raw_json': raw,
                'classified_topics': topics_val or [],
                'stages_info': row['stages_info'] or ''
            })
        return projects
    async def get_projects_by_topic(self, topic: str) -> list:
        query = """
            SELECT
                external_id as id,
                title,
                department,
                creation_date,
                publication_date,
                stage,
                status,
                stages_info
            FROM projects
            WHERE topics ?| $1
            ORDER BY publication_date DESC NULLS LAST
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, [topic])

        projects = []
        for row in rows:
            projects.append({
                'id': row['id'],
                'title': row['title'],
                'developedDepartment': {'description': row['department']} if row['department'] else None,
                'creationDate': row['creation_date'].isoformat() if row['creation_date'] else None,
                'publicationDate': row['publication_date'].isoformat() if row['publication_date'] else None,
                'stage': row['stage'],
                'status': row['status'],
                'stages_info': row['stages_info'] or '',
            })
        return projects
    async def has_any_projects(self) -> bool:
        query = "SELECT EXISTS(SELECT 1 FROM projects LIMIT 1)"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query)
        # -------------------- ЗАКРЫТИЕ --------------------
    async def close(self):
        if self.pool:
            await self.pool.close()
            print("🔌 PostgreSQL соединение закрыто")