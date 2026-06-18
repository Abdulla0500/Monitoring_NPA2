from Dictionaries import TOPICS
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Set
async def show_search_menu(callback,db):
    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)

    current_subs = await db.get_user_subscriptions(user_id)
    selected = set(current_subs)

    if not hasattr(callback.bot, 'user_data'):
        callback.bot.user_data = {}
    
    if user_id not in callback.bot.user_data:
        callback.bot.user_data[user_id] = {}
    
    user_data = callback.bot.user_data[user_id]

    if 'selected_topics' not in user_data:
        user_data['selected_topics'] = set(current_subs)

    selected: Set[str] = user_data['selected_topics']

    keyboard = []
    row = []

    for i, (topic_code, topic_name) in enumerate(TOPICS.items(), 1):
        button_text = f"✅ {topic_name}" if topic_code in selected else topic_name
        
        row.append(
            InlineKeyboardButton(
                text=button_text,                   
                callback_data=f"toggle_{topic_code}"
            )
        )

        if i % 2 == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(text="💾 Сохранить", callback_data="save_subscriptions")
    ])
    keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    ])

    await callback.message.edit_text(
        "📋 Выберите темы (можно несколько):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
async def handle_toggle(callback,db):
    """Обрабатывает нажатие на тему (toggle)"""
    await callback.answer()

    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    topic = callback.data.replace("toggle_", "")

    user_data = callback.bot.user_data.get(user_id, {})
    selected: set = user_data.get('selected_topics', set())

    if topic in selected:
        selected.remove(topic)
    else:
        selected.add(topic)

    user_data['selected_topics'] = selected

    await show_search_menu(callback,db)

async def save_subscriptions(callback,db):
    await callback.answer()

    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    user_data = callback.bot.user_data.get(user_id, {})
    selected_topics: set = user_data.get('selected_topics', set())

    if not selected_topics:
        await callback.message.edit_text(
            "❌ Вы не выбрали ни одной темы.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="menu_search")
            ]])
        )
        return

    current_subs = set(await db.get_user_subscriptions(user_id))

    for topic in current_subs - selected_topics:
        await db.remove_subscription(user_id, topic)

    for topic in selected_topics - current_subs:
        await db.add_subscription(user_id, topic)

    if user_id in callback.bot.user_data:
        callback.bot.user_data[user_id].pop('selected_topics', None)

    topic_names = [TOPICS.get(t, t) for t in selected_topics]
    topics_str = "\n• " + "\n• ".join(topic_names)

    await callback.message.edit_text(
        f"✅ **Подписки успешно обновлены!**\n\n"
        f"Вы подписаны на следующие темы:\n{topics_str}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")
        ]])
    )