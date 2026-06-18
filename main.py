from database import Database
from config import config1
from aiogram import Bot, Dispatcher, types, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram.filters import Command
import asyncio
import buttons.handbook as h
import buttons.last_updates as l
import buttons.subscriptions as s
import buttons.current_projects as c
import buttons.settings as set
import buttons.archive_projects as arch
import logging
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from buttons.project_search import (
    SearchStates, start_search, process_search_query, cancel_search, send_search_results,
    filter_developer, filter_stage, filter_procedure, filter_status, filter_pubdate,
    filter_discussion, filter_reset, save_filter_value, filter_search_execute,
    back_to_filters, process_date_start, process_date_end, filter_date_skip_start,
    filter_date_skip_end, dev_page_callback, filter_topic, start_developer_search,
    process_developer_search, back_to_developer_list, dev_reset_filter,process_title_filter,filter_title
)
from buttons.favorite import(show_favorite_projects, send_favorite_chunked)
from notifier import send_daily_notifications
db = Database()
storage = MemoryStorage()
bot = None  


dp = Dispatcher(storage=storage)
router = Router()

router = Router()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

def get_main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔍 Поиск проекта", callback_data="search_start")],
        [InlineKeyboardButton(text="📋 Текущие проекты", callback_data="menu_current")],
        [InlineKeyboardButton(text="📌 Подписки", callback_data="menu_search")],
        [InlineKeyboardButton(text="📁 Мои проекты", callback_data="menu_favorite")],
        [InlineKeyboardButton(text="🗂 Архив", callback_data="menu_archive")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")],
        [InlineKeyboardButton(text="📅 Последние обновления", callback_data="menu_last")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user

    await db.add_user(
        telegram_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )

    logger.info(f"Пользователь: {user.first_name} (ID: {user.id})")

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"📋 **Выберите пункт меню:**"
    )

    await message.answer(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


@router.callback_query()
async def button_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = callback.data  
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} нажал кнопку: {data}")

    if data == "menu_current":
        await c.show_current_projects(callback,db)
    elif data == "menu_search":
        await s.show_search_menu(callback,db)
    elif data.startswith("toggle_"):
        await s.handle_toggle(callback,db)
    elif data.startswith("unsub_"):
        user_id = await db.get_user_id(callback.from_user.id)
        topic = data.replace("unsub_", "")
        success = await db.remove_subscription(user_id, topic)
        if success:
            await callback.message.edit_text(
                f"✅ Вы отписались от темы `{topic}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
                ]])
            )
        else:
            await callback.message.edit_text("❌ Не удалось отписаться (возможно, подписки не было).")
    elif data == "save_subscriptions":
        await s.save_subscriptions(callback,db)
    elif data == "search_start":
        await start_search(callback, state)
    elif data == "filter_developer":
        await filter_developer(callback, state, db)
    elif data.startswith("dev_page_"):
        await dev_page_callback(callback, state)
    elif data == "filter_stage":
        await filter_stage(callback, state)
    elif data == "filter_procedure":
        await filter_procedure(callback, state)
    elif data == "filter_topic":
        await filter_topic(callback, state)
    elif data == "developer_search":
        await start_developer_search(callback, state)
    elif data == "filter_status":
        await filter_status(callback, state)
    elif data == "filter_pubdate":
        await filter_pubdate(callback, state)
    elif data == "filter_discussion":
        await filter_discussion(callback, state)
    elif data == "filter_topic":
        await filter_topic(callback, state)
    elif data == "developer_search":
        await start_developer_search(callback, state)
    elif data == "filter_title":
        await filter_title(callback, state)
    elif data == "back_to_developer_list":
        await back_to_developer_list(callback, state)
    elif data == "dev_reset_filter":
        await dev_reset_filter(callback, state)
    elif data == "filter_reset":
        await filter_reset(callback, state)
    elif data == "menu_favorite":
        await show_favorite_projects(callback, db)
    elif data.startswith("fav_page_"):
        start_index = int(data.split("_")[2])
        user_id = await db.get_user_id(callback.from_user.id)
        projects = await db.get_saved_projects(user_id)
        await send_favorite_chunked(callback, projects, db, start_index, chunk_size=5)
    elif data.startswith("add_fav_"):
        external_id = int(data.split("_")[2])
        user_id = await db.get_user_id(callback.from_user.id)
        success = await db.add_saved_project(user_id, external_id)
        if success:
            await callback.message.answer("✅ Проект добавлен в раздел «Мои проекты»")
        else:
            await callback.message.answer("ℹ️ Этот проект уже есть в вашем списке «Мои проекты»")
        await callback.answer()  # убираем «часики» на кнопке
    elif data.startswith("remove_fav_"):
        external_id = int(data.split("_")[2])
        user_id = await db.get_user_id(callback.from_user.id)
        success = await db.remove_saved_project(user_id, external_id)
        if success:
            await callback.answer("🗑 Проект удалён из «Моих проектов»", show_alert=True)
        else:
            await callback.answer("❌ Не удалось удалить", show_alert=True)
    elif data == "filter_search_execute":
        await filter_search_execute(callback, state, db)
    elif data == "back_to_filters":
        await back_to_filters(callback, state)
    elif data == "filter_date_skip_start":
        await filter_date_skip_start(callback, state)
    elif data == "filter_date_skip_end":
        await filter_date_skip_end(callback, state)
    elif data.startswith("filter_dev_idx_") or data.startswith("filter_stage_val_") or \
        data.startswith("filter_proc_idx_") or data.startswith("filter_status_val_") or \
        data.startswith("filter_topic_idx_"):
        await save_filter_value(callback, state)
    elif data == "cancel_search":
        await cancel_search(callback, state)
    elif data.startswith("search_page|"):
        _, page_str = data.split("|")
        page = int(page_str)
        # Восстанавливаем данные из состояния
        user_data = await state.get_data()
        projects = user_data.get("search_results", [])
        query = user_data.get("search_query", "")
        if projects:
            await send_search_results(callback, projects, query, page, state)
        else:
            await callback.message.edit_text("❌ Данные поиска устарели. Начните новый поиск.")
            await start_search(callback, state)
    elif data == "menu_archive":
        await arch.show_archive_topics(callback)
    elif data.startswith('archive_'):
        topic = data.replace('archive_', '')
        await arch.show_archive_projects(callback, topic, db)
    elif data.startswith('continue_archive|'):          # 👈 сначала специфичный
        _, topic, start_index_str = data.split('|')
        start_index = int(start_index_str)
        user_id = await db.get_user_id(callback.from_user.id)
        archive_key = f"archive_{topic}_{user_id}"
        filtered_projects = arch.projects_cache.get(archive_key, [])
        if filtered_projects:
            await arch.send_archive_chunked(
                callback=callback,
                projects=filtered_projects,
                topic=topic,
                start_index=start_index,
                chunk_size=20
            )
        else:
            await arch.show_archive_projects(callback, topic, db)
    elif data.startswith("continue_"):
        parts = data.split('_')
        start_index = int(parts[1])
        
        projects = callback.bot.user_data.get('current_projects', [])
        
        if not projects:
            await callback.message.edit_text(
                "❌ Список проектов не найден. Пожалуйста, вернитесь в меню и выберите 'Текущие проекты' заново.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
                ]])
            )
            return
        
        user_id = await db.get_user_id(callback.from_user.id)
        user_role = await db.get_user_role(user_id)
        
        await c.send_projects_chunked(
            query=callback,
            projects=projects,
            user_role=user_role,
            title_prefix=f"📋 **Текущие активные проекты**\n📊 Всего: {len(projects)}\n",
            start_index=start_index,
            chunk_size=10
        )
    elif data == "menu_settings":
        await set.show_settings_menu(callback,db)
    elif data.startswith('select_role_'):
        role_id = data.replace('select_role_', '')
        await set.handle_role_selection(callback, role_id, db)
    elif data.startswith('settings_time'):
        await set.show_time_selection(callback,db)
    elif data.startswith("set_time_"):
        time_str = data.replace("set_time_", "")
        success = await db.set_notification_time(user_id, time_str)

        if success:
            await callback.message.edit_text(
                f"✅ Время уведомлений установлено на {time_str}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[  
                    [InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="menu_settings")]
                ])
            )
        else:
            await callback.answer("Ошибка сохранения")
    elif data == "change_role":
        await set.show_role_selection(callback,db)
    elif data == "menu_help":
        await h.show_help(callback)
    elif data == "menu_last":
        await l.show_last_filter_menu(callback)
    elif data.startswith("last_period_"):
        period = data.replace("last_period_", "")
        await l.show_last_scope_menu(callback, period)
    elif data.startswith("last_scope_"):
        parts = data.split("_")
        scope = parts[2]
        period = parts[3] if len(parts) > 3 else "7"
        await l.show_last_projects(callback,db, period, scope)
    elif data == "back_to_main":
        await callback.message.edit_text(
            "📋 **Выберите пункт меню:**",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
@router.message(SearchStates.waiting_for_query)
async def handle_search_query(message: types.Message, state: FSMContext):
    await process_search_query(message, state, db)

@router.message(SearchStates.waiting_for_date_start)
async def handle_date_start(message: types.Message, state: FSMContext):
    await process_date_start(message, state)

@router.message(SearchStates.waiting_for_date_end)
async def handle_date_end(message: types.Message, state: FSMContext):
    await process_date_end(message, state)

@router.message(SearchStates.waiting_for_developer_search)
async def handle_developer_search(message: types.Message, state: FSMContext):
    await process_developer_search(message, state, db)

@router.message(SearchStates.waiting_for_title_filter)
async def handle_title_filter(message: types.Message, state: FSMContext):
    await process_title_filter(message, state)
async def main():
    print("🚀 Запуск бота...")
    await db.connect()
    await db.create_tables()
    bot = Bot(token=config1.BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(router)
    scheduler = AsyncIOScheduler()
    
    
    scheduler.add_job(send_daily_notifications, CronTrigger(minute="*"), args=(bot,))
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())