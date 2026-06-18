
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
from fetcher import RegulationAPI
from classifier import ProjectClassifier
from buttons.supporting import fetch_with_retry_simple, split_long_message_for_query
from Dictionaries import TOPICS_SHORT

api = RegulationAPI()
projects=None

async def show_last_filter_menu(query):
    keyboard = [
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="last_period_today")],
        [InlineKeyboardButton(text="📆 Вчера", callback_data="last_period_yesterday")],
        [InlineKeyboardButton(text="📆 За 3 дня", callback_data="last_period_3")],
        [InlineKeyboardButton(text="📆 За 7 дней", callback_data="last_period_7")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]

    await query.message.edit_text(
        "📅 **Выберите период:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

async def show_last_scope_menu(query, period: str):
    keyboard = [
        [InlineKeyboardButton(text="🔥 Только мои подписки", 
                              callback_data=f"last_scope_mine_{period}")],
        [InlineKeyboardButton(text="🌍 Все проекты", 
                              callback_data=f"last_scope_all_{period}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_last")]
    ]
    await query.message.edit_text(
        "🔎 **Показать проекты:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

async def show_last_projects(query,db, period="7", scope="all"):
    await query.message.edit_text("🔍 Загружаю проекты...")
    telegram_id = query.from_user.id
    user_id = await db.get_user_id(telegram_id)
    user_topics = set(await db.get_user_subscriptions(user_id))
    today = datetime.now().date()

    if period == "today":
        start_date = today
        period_label = "сегодня"
    elif period == "yesterday":
        start_date = today - timedelta(days=1)
        period_label = "вчера"
    elif period == "3":
        start_date = today - timedelta(days=3)
        period_label = "за 3 дня"
    elif period == "7":
        start_date = today - timedelta(days=7)
        period_label = "за 7 дней"
    else:
        start_date = today - timedelta(days=7)
        period_label = "за 7 дней"
    global projects
    
    if projects is None:
        projects = await fetch_with_retry_simple(
            api.fetch_all_projects_optimized,
            max_retries=3,
            delay=2,
            max_pages=50
        )

    if not projects:
        await query.message.edit_text(
            "❌ Не удалось загрузить проекты",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
            ]])
        )
        return


    matching_projects = []

    for p in projects:
        date_str = p.get("publicationDate") or p.get("creationDate")
        if not date_str:
            continue

        try:
            project_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        if project_date < start_date:
            continue

        department = p.get('developedDepartment', {}).get('description')
        topics = ProjectClassifier.classify(
            title=p.get("title", ""),
            department=department
        )
        if scope == "mine":
            if not user_topics:
                continue
            if not (set(topics) & user_topics):
                continue

        p["classified_topics"] = topics
        matching_projects.append(p)

    matching_projects.sort(
        key=lambda x: x.get("publicationDate") or x.get("creationDate") or "",
        reverse=True
    )

    if not matching_projects:
        await query.message.edit_text(
            f"❌ Нет проектов {period_label}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="menu_last")
            ]])
        )
        return

    scope_label = "только мои подписки" if scope == "mine" else "все проекты"

    text = (
        f"📅 **Проекты {period_label}**\n\n"
        f"🔎 Фильтр: {scope_label}\n\n"
        f"📊 Найдено: **{len(matching_projects)}**\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"

    )

    for i, p in enumerate(matching_projects, 1):
        title = p.get("title", "Без названия")
        dept = p.get("developedDepartment", {}).get("description", "Не указано")
        date = p.get("publicationDate") or p.get("creationDate", "")
        project_id = p.get("id")

        topics = p.get("classified_topics", [])
        topic_str = " ".join([TOPICS_SHORT.get(t, t) for t in topics]) if topics else "НПА"

        url = f"https://regulation.gov.ru/projects#npa={project_id}"

        text += f"{i}. {topic_str}\n\n"
        text += f"   📌 {title}\n\n"
        text += f"   🏢 {dept[:100]}\n\n"
        text += f"   📅 {date[:10] if date else 'Нет даты'}\n\n"
        text += f"   🔗 {url}\n\n"
        text += "━━━━━━━━━━━━━━━━━━\n\n"

    await split_long_message_for_query(
        query,
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="◀️ Назад в меню", 
                    callback_data="back_to_main"
                )
            ]]
        )
    )