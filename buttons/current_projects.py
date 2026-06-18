from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fetcher import RegulationAPI
import asyncio
from Dictionaries import active_statuses, completed_statuses
import logging
from datetime import datetime
from buttons.supporting import fetch_with_retry_simple, split_long_message_for_query
import time
from roles import format_project_by_role 
api = RegulationAPI()
logger = logging.getLogger(__name__)
async def show_current_projects(callback, db):
    await callback.message.edit_text("🔍 Загружаю текущие проекты по вашим подпискам...")

    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    user_role =await db.get_user_role(user_id)
    user_subs =await db.get_user_subscriptions(user_id)
    logger.info(f"Загружены подписки для пользователя {user_id}: {user_subs}")

    if not user_subs:
        await callback.message.edit_text(
            "❌ У вас нет активных подписок.\n\nХотите подписаться?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Перейти к подписке", callback_data="menu_search")],
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
            ])
        )
        return

    if not hasattr(callback.bot, 'user_data'):
        callback.bot.user_data = {}
    if 'all_projects' not in callback.bot.user_data:
        callback.bot.user_data['all_projects'] = None

    all_projects = callback.bot.user_data['all_projects']
    if all_projects is None:
        await callback.message.edit_text("📡 Загружаю проекты с regulation.gov.ru...")
        all_projects = await api.fetch_all_projects_optimized(max_pages=500, page_size=20, max_concurrent=20)
        callback.bot.user_data['all_projects'] = all_projects

    if not all_projects:
        await callback.message.edit_text(
            "❌ Не удалось загрузить проекты.\nПопробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
            ]])
        )
        return
    
    projects_with_dates = [p for p in all_projects if p.get('last_modified')]
    matching_projects = []
    today = datetime.now().date()

    for p in all_projects:
        topics = p.get('classified_topics', [])
        if not topics or not set(topics).intersection(set(user_subs)):
            continue

        is_active = False
        status = p.get('status', '')

        if p.get('last_modified'):
            try:
                last_mod = datetime.strptime(p['last_modified'], '%Y-%m-%d').date()
                days_since_change = (today - last_mod).days
                if days_since_change <= 90:
                    is_active = True
                    logger.debug(f"Проект {p.get('id')} активен по дате изменения: {days_since_change} дней")
            except (ValueError, TypeError):
                pass

        if not is_active:
            if status in active_statuses:
                is_active = True
                logger.debug(f"Проект {p.get('id')} активен по статусу: {status}")
            elif not status:
                is_active = True
                logger.debug(f"Проект {p.get('id')} активен (пустой статус)")
            elif status not in completed_statuses:
                is_active = True
                logger.debug(f"Проект {p.get('id')} активен (неизвестный статус: {status})")

        if not is_active:
            end_date_str = p.get('endPublicDiscussion')
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
                    days_since_end = (today - end_date).days
                    if days_since_end <= 30:
                        is_active = True
                        logger.debug(f"Проект {p.get('id')} активен по дате окончания: {days_since_end} дней")
                except (ValueError, TypeError):
                    pass

        if status in completed_statuses:
            if p.get('last_modified'):
                try:
                    last_mod = datetime.strptime(p['last_modified'], '%Y-%m-%d').date()
                    days_since_change = (today - last_mod).days
                    if days_since_change <= 30:
                        is_active = True
                        logger.debug(f"Завершенный проект {p.get('id')} активен по дате изменения: {days_since_change} дней")
                    else:
                        is_active = False
                except (ValueError, TypeError):
                    is_active = False
            else:
                is_active = False

        if is_active:
            matching_projects.append(p)

    logger.info(f"Найдено {len(matching_projects)} активных проектов из {len(all_projects)}")

    if not matching_projects:
        await callback.message.edit_text(
            "❌ Нет активных проектов по вашим подпискам.\n\n"
            "Попробуйте посмотреть архив или изменить подписки.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗂 Перейти в архив", callback_data="menu_archive")],
                [InlineKeyboardButton(text="🔍 Изменить подписки", callback_data="menu_search")],
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
            ])
        )
        return
    if user_role == 'lawyer':
        projects_without_stages = [p for p in matching_projects if not p.get('stages')]
        if projects_without_stages:
            logger.info(f"⏳ Загружаем этапы для {len(projects_without_stages)} активных проектов пользователя...")
            await load_stages_parallel(projects_without_stages, limit=10)
            logger.info(f"✅ Этапы загружены для {len(projects_without_stages)} проектов")

    callback.bot.user_data['current_projects'] = matching_projects

    title = f"📋 **Текущие активные проекты**\n📊 Всего: {len(matching_projects)}\n"

    if user_role == 'lawyer':
        projects_with_stages = len([p for p in matching_projects if p.get('stages')])
        if projects_with_stages == len(matching_projects):
            title += "📋 Все проекты с этапами\n\n"
        else:
            title += f"📋 Этапы загружены для {projects_with_stages} из {len(matching_projects)} проектов\n\n"
    elif projects_with_dates:
        title += f"📅 Сортировка по дате изменения: {len([p for p in matching_projects if p.get('last_modified')])} проектов\n\n"
    else:
        title += f"📅 Сортировка по дате публикации\n\n"

    await send_projects_chunked(
        query=callback,
        projects=matching_projects,
        user_role=user_role,
        title_prefix=title,
        start_index=0,
        chunk_size=10
    )

async def send_projects_chunked(query, projects, user_role, title_prefix="📋 **Текущие проекты**", start_index=0,
                                chunk_size=10, additional_data=None):
    total_projects = len(projects)
    end_index = min(start_index + chunk_size, total_projects)

    current_chunk = projects[start_index:end_index]
    text = f"{title_prefix}\n\n"
    text += f"📊 Найдено проектов: {total_projects}\n"
    text += f"📄 Показано {start_index + 1}-{end_index} из {total_projects}\n\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"

    for i, p in enumerate(current_chunk, start=start_index + 1):
        project_text = format_project_by_role(p, user_role)
        text += f"{i}. {project_text}\n"

    keyboard = []

    if end_index < total_projects:
        callback_data = f"continue_{start_index + chunk_size}"
        if additional_data:
            callback_data += f"_{additional_data}"
        keyboard.append([
            InlineKeyboardButton(
                text=f"▶️ Продолжить ({end_index + 1}-{min(end_index + chunk_size, total_projects)} из {total_projects})",
                callback_data=callback_data
            )
        ])

    keyboard.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])
    logger.info(f"Создаю клавиатуру: {keyboard}")
    logger.info(f"Тип клавиатуры: {type(keyboard)}")
    await split_long_message_for_query(
        query,
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

async def load_stages_parallel(projects, limit=10):
    sem = asyncio.Semaphore(limit)

    loaded = 0
    total = len(projects)
    start_time = time.time()

    async def fetch_stages(project):
        nonlocal loaded
        project_id = project.get("id")
        if not project_id:
            return

        async with sem:
            try:
                stages = await fetch_with_retry_simple(
                    api.fetch_project_stages,
                    max_retries=2,
                    delay=1,
                    project_id=project_id
                )
                if stages:
                    project["stages"] = stages
                    loaded += 1

            except Exception as e:
                logger.error(f"Ошибка загрузки этапов для {project_id}: {e}")

    tasks = [fetch_stages(p) for p in projects]
    await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    if loaded > 0:
        logger.info(f"✅ Загружены этапы для {loaded} из {total} проектов за {elapsed:.1f} сек")