from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Database

async def show_favorite_projects(callback, db: Database):
    user_id = await db.get_user_id(callback.from_user.id)
    projects = await db.get_saved_projects(user_id)

    if not projects:
        await callback.message.edit_text(
            "📭 У вас пока нет сохранённых проектов.\nЧтобы добавить проект, найдите его через поиск или в других разделах и нажмите «⭐ Добавить в мои проекты».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
            ])
        )
        return

    # Отправляем проекты чанками по 5 штук с возможностью удаления
    await send_favorite_chunked(callback, projects, db, start_index=0, chunk_size=5)

async def send_favorite_chunked(callback, projects, db: Database, start_index: int, chunk_size: int):
    total = len(projects)
    end_index = min(start_index + chunk_size, total)
    chunk = projects[start_index:end_index]

    text = f"📁 **Мои проекты**\n📊 Всего сохранено: {total}\n\n"
    for i, proj in enumerate(chunk, start=1):
        title = proj.get('title', 'Без названия')
        dept = proj.get('developedDepartment', {}).get('description', 'Не указан')
        text += f"{i}. **{title}**\n\n   🏢 {dept}\n\n"
        # Можно добавить ссылку
        proj_id = proj.get('id')
        text += f"   🔗 [Ссылка](https://regulation.gov.ru/projects#npa={proj_id})\n\n"

    # Клавиатура: кнопка удалить для каждого проекта
    keyboard = []
    for proj in chunk:
        proj_id = proj.get('id')
        title_short = proj.get('title', 'Проект')[:30]
        keyboard.append([InlineKeyboardButton(text=f"🗑 Удалить: {title_short}", callback_data=f"remove_fav_{proj_id}")])

    # Пагинация
    nav = []
    if start_index > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"fav_page_{start_index - chunk_size}"))
    if end_index < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"fav_page_{end_index}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)