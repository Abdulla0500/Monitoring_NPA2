
from Dictionaries import TOPICS_SHORT,USER_ROLES
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import logging
logger = logging.getLogger(__name__)
async def show_settings_menu(callback, db):
    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    user_topics = set(await db.get_user_subscriptions(user_id))
    current_role =await db.get_user_role(user_id)
    role_name = USER_ROLES.get(current_role, {}).get('name', 'Не выбрана')

    if user_topics:
        sorted_subs = sorted(user_topics)

        items = [TOPICS_SHORT.get(topic, topic) for topic in sorted_subs]

        rows = []
        for i in range(0, len(items), 2):
            left = items[i]
            if i + 1 < len(items):
                right = items[i + 1]
                rows.append(f"{left:<20}{right:<20}")
            else:
                rows.append(f"{left:<20}")

        subs_text = "📋 **Текущие подписки:**\n\n" + "\n\n".join(rows) + f"\n\n📊 Всего: {len(user_topics)} подписок\n"
    else:
        subs_text = "❌ У вас нет активных подписок\n\n"

    keyboard = [
        [InlineKeyboardButton(text=f"👤 Сменить роль (сейчас: {role_name})", callback_data="change_role")],
        [InlineKeyboardButton(text="🔧 Управление подписками", callback_data="menu_search")],
        [InlineKeyboardButton(text="⏰ Время уведомлений", callback_data="settings_time")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
    ]

    await callback.message.edit_text(
        text=f"⚙️ **Настройки**\n\nТекущая роль: {role_name}\n\n{subs_text}\n\nВыберите что хотите изменить:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
async def show_role_selection(callback,db):
    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    current_role =await db.get_user_role(user_id)
    keyboard = []

    for role_id, role_info in USER_ROLES.items():
        button_text = f"{role_info['name']} - {role_info['description']}"
        if role_id == current_role:
            button_text = f"✅ {button_text} (текущая)"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"select_role_{role_id}")])

    keyboard.append([InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="menu_settings")])

    text = "👤 **Смена роли**\n\nВыберите новую роль — от этого будет зависеть формат отображения проектов:\n\n"
    for role_id, role_info in USER_ROLES.items():
        text += f"**{role_info['name']}**\n└ {role_info['description']}\n\n"

    await callback.message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def handle_role_selection(callback, role_id,db):
    telegram_id = callback.from_user.id
    user_id = await db.get_user_id(telegram_id)
    current_role = await db.get_user_role(user_id)

    if role_id == current_role:
        await callback.answer("Это ваша текущая роль")
        return

    success =await db.set_user_role(user_id, role_id)
    if success:
        role_name = USER_ROLES.get(role_id, {}).get('name', role_id)
        text = f"✅ Роль успешно изменена на **{role_name}**!\n\nТеперь проекты будут отображаться в новом формате."
        keyboard = [
            [InlineKeyboardButton(text="⚙️ Вернуться в настройки", callback_data="menu_settings")],
            [InlineKeyboardButton(text="📋 В главное меню", callback_data="back_to_main")]
        ]
        await callback.message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        logger.info(f"Пользователь {user_id} сменил роль на: {role_name}")
    else:
        await callback.message.edit_text(
            text="❌ Ошибка при смене роли. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Назад", callback_data="menu_settings")
            ]])
        )
async def show_time_selection(callback,db):
    current_time = await db.get_notification_time(callback.from_user.id)

    keyboard = []
    times = ["06:00", "07:00", "08:00", "09:00","09:42","09:56", "10:05",
             "12:00", "15:00", "19:29"]

    for t in times:
        text = f"✅ {t}" if t == current_time else t
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"set_time_{t}")])

    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_settings")])

    await callback.message.edit_text(
        f"⏰ **Выберите время уведомлений**\n\n"
        f"🕐 Бот использует время **UTC (Всемирное координированное время)**\n\n"
        f"💡 **Как перевести ваше местное время в UTC:**\n\n"
        f"🇷🇺  **Для России (MSK/московское время):**\n"
        f"• Москва (UTC+3): вычитайте 3 часа\n\n"
        f"  Пример: хотите в 10:00 MSK → выбирайте 07:00 UTC\n\n",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )