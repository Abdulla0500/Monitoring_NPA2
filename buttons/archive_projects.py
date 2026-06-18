from Dictionaries import TOPICS_SHORT,TOPICS
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fetcher import RegulationAPI 
from buttons.supporting import fetch_with_retry_simple, split_long_message_for_query,format_project_stage, make_json_serializable
import logging
from datetime import datetime
api = RegulationAPI()
all_projects=[]
logger = logging.getLogger(__name__)

projects_cache = {}  

async def load_projects_from_db(db):
    try:
        rows = await db.get_all_projects()
        if not rows:
            return None
        projects = []
        for row in rows:
            project = row.get('raw_json')
            # Проверяем именно на None, а не на "пустое значение"
            if project is not None:
                if 'classified_topics' not in project:
                    project['classified_topics'] = row.get('topics', [])
                projects.append(project)
            else:
                # Используем правильное имя поля 'id'
                logger.warning(f"Проект {row.get('id')} не имеет raw_json")
        logger.info(f"Загружено {len(projects)} проектов из БД")
        return projects
    except Exception as e:
        logger.error(f"Ошибка загрузки проектов из БД: {e}")
        return None

async def save_projects_to_db(db, projects):
    saved = 0

    for p in projects:
        external_id_raw = p.get('id')
        if not external_id_raw:
            continue

        try:
            external_id = int(str(external_id_raw).strip())
        except (ValueError, TypeError):
            logger.warning(f"Пропуск проекта с некорректным id: {external_id_raw}")
            continue

        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                return None

        creation_date = parse_date(p.get('creationDate'))
        publication_date = parse_date(p.get('publicationDate'))

        topics_value = p.get('classified_topics') or []

        if isinstance(topics_value, set):
            topics_value = list(topics_value)

        topics_value = make_json_serializable(topics_value)

        if not isinstance(topics_value, list):
            topics_value = []

        clean_project = make_json_serializable(p)

        project_data = {
            'external_id': external_id,
            'title': p.get('title', ''),
            'department': (p.get('developedDepartment') or {}).get('description', ''),
            'creation_date': creation_date,
            'publication_date': publication_date,
            'stage': p.get('stage'),
            'status': p.get('status'),
            'project_type_name': (p.get('projectType') or {}).get('description', ''),
            'procedure_name': (p.get('procedure') or {}).get('description', ''),
            'raw_json': clean_project,
            'topics': topics_value,
            'stages_info': format_project_stage(p) or ""
        }

        try:
            await db.upsert_project(project_data)
            saved += 1
        except Exception as e:
            logger.error(f"Ошибка сохранения проекта {external_id}: {e}")

    logger.info(f"Сохранено/обновлено {saved} проектов из {len(projects)}")
async def show_archive_topics(callback):
    keyboard = []
    row = []
    for i, (topic_code, topic_name) in enumerate(TOPICS.items(), 1):
        button = InlineKeyboardButton(text=topic_name, callback_data=f"archive_{topic_code}")
        row.append(button)
        if i % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])

    await callback.message.edit_text(
        "🗂 **Архив проектов\n\nВыберите тему для просмотра:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
async def show_archive_projects(callback, topic, db):
    await callback.answer()
    await callback.message.edit_text(f"🔍 Загружаю архив проектов по теме {TOPICS_SHORT.get(topic, topic)}...")

    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)

    cache_key = "archive_all_projects"
    all_projects = projects_cache.get(cache_key)

    if all_projects is None:
        all_projects = await load_projects_from_db(db)
        if all_projects:
            logger.info(f"Загружено {len(all_projects)} проектов из БД")
            projects_cache[cache_key] = all_projects
        else:
            await callback.message.edit_text("📡 Загружаю проекты с regulation.gov.ru (это может занять время, около 8 минут)...")

            all_projects = await fetch_with_retry_simple(
                lambda: api.fetch_all_projects_optimized(max_pages=None, page_size=20, max_concurrent=20),
                max_retries=3, delay=2
            )
            if all_projects:
                logger.info(f"Загружено {len(all_projects)} проектов из API")
                await save_projects_to_db(db, all_projects)
                projects_cache[cache_key] = all_projects  # исправлено
            else:
                await callback.message.edit_text(
                    "❌ Не удалось загрузить проекты.\nПопробуйте позже.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="◀️ Назад к темам", callback_data="menu_archive")
                    ]])
                )
                return

    filtered_projects = []
    for p in all_projects:
        p_topics = p.get('classified_topics', [])
        if topic in p_topics:
            p['classified_topics'] = p_topics
            filtered_projects.append(p)

    filtered_projects.sort(
        key=lambda x: x.get('publicationDate') or x.get('creationDate', '') or '0000-00-00',
        reverse=True
    )

    if not filtered_projects:
        await callback.message.edit_text(
            f"❌ Нет проектов по теме {TOPICS_SHORT.get(topic, topic)}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Поиск проекта", callback_data="search_start"),
                InlineKeyboardButton(text="◀️ Назад к темам", callback_data="menu_archive")
            ]])
        )
        return

    text = f"🗂 **Архив {TOPICS_SHORT.get(topic, topic)} (все проекты)**\n\n"
    text += f"📊 Найдено проектов: {len(filtered_projects)}\n\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"

    count = 0
    for p in filtered_projects:
        count += 1
        title = p.get('title', 'Без названия')
        dept = p.get('developedDepartment', {}).get('description', 'Не указано')
        date = p.get('publicationDate') or p.get('creationDate', '')
        date_str = date[:10] if date else 'Дата не указана'
        project_id = p.get('id')
        stage_info = format_project_stage(p)
        url = f"https://regulation.gov.ru/projects#npa={project_id}"

        text += f"{count}. **{TOPICS_SHORT.get(topic, topic)}**\n\n"
        text += f"   📌 {title}\n\n"
        text += f"   🏢 {dept}\n\n"

        if stage_info:
            for line in stage_info.split('\n'):
                text += f"   {line}\n"

        text += f"   📅 {date_str}\n\n"
        text += f"   🔗 {url}\n\n"
        text += "━━━━━━━━━━━━━━━━━━\n\n"

    archive_key = f"archive_{topic}_{user_id}"
    projects_cache[archive_key] = filtered_projects
    await send_archive_chunked(
        callback=callback,
        projects=filtered_projects,
        topic=topic,
        start_index=0,
        chunk_size=20
    )


async def send_archive_chunked(callback, projects, topic, start_index=0, chunk_size=20):
    total_projects = len(projects)
    end_index = min(start_index + chunk_size, total_projects)

    current_chunk = projects[start_index:end_index]

    text = f"🗂 **Архив {TOPICS_SHORT.get(topic, topic)} (все проекты)**\n\n"
    text += f"📊 Найдено проектов: **{total_projects}**\n"
    text += f"📄 Показано {start_index + 1}-{end_index} из {total_projects}\n\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"

    for i, p in enumerate(current_chunk, start=start_index + 1):
        title = p.get('title', 'Без названия')
        dept = p.get('developedDepartment', {}).get('description', 'Не указано')
        date = p.get('publicationDate') or p.get('creationDate', '')
        date_str = date[:10] if date else 'Дата не указана'
        project_id = p.get('id')
        stage_info = format_project_stage(p)
        url = f"https://regulation.gov.ru/projects#npa={project_id}"

        text += f"{i}. **{TOPICS_SHORT.get(topic, topic)}**\n\n"
        text += f"   📌 {title}...\n\n"
        text += f"   🏢 {dept}\n\n"

        if stage_info:
            for line in stage_info.split('\n'):
                text += f"   {line}\n"

        text += f"   📅 {date_str}\n\n"
        text += f"   🔗 {url}\n\n"
        text += "━━━━━━━━━━━━━━━━━━\n\n"

    keyboard = []

    if end_index < total_projects:
        keyboard.append([
            InlineKeyboardButton(
                text=f"▶️ Продолжить ({end_index + 1}-{min(end_index + chunk_size, total_projects)} из {total_projects})",
                callback_data=f"continue_archive|{topic}|{start_index + chunk_size}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text="◀️ Назад к темам", callback_data="menu_archive"),
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")
    ])

    await split_long_message_for_query(
        callback,
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )