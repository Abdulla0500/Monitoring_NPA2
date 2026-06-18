# buttons/project_search.py
import logging
import asyncio
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from database import Database
from Dictionaries import STAGE_DESCRIPTIONS, STATUS_DESCRIPTIONS, PROCEDURE_TYPES, TOPICS

logger = logging.getLogger(__name__)


class SearchStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_filter = State()
    waiting_for_filter_value = State()
    waiting_for_title_filter = State()
    waiting_for_date_start = State()
    waiting_for_date_end = State()
    waiting_for_developer_search = State()  # поиск по разработчикам


# ---------- Универсальная отправка длинных сообщений ----------
async def send_long_message(target, text, parse_mode="Markdown", reply_markup=None):
    """
    Отправляет длинное сообщение, разбивая на части по 4096 символов.
    target: может быть CallbackQuery или Message
    """
    if len(text) <= 4096:
        if hasattr(target, 'message'):  # CallbackQuery
            await target.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:  # Message
            await target.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return

    # Разбиваем на части по строкам
    parts = []
    current = ""
    for line in text.split('\n'):
        if len(current) + len(line) + 1 <= 4096:
            current += ('\n' + line) if current else line
        else:
            parts.append(current)
            current = line
    if current:
        parts.append(current)

    # Первая часть
    if hasattr(target, 'message'):
        await target.message.edit_text(parts[0], parse_mode=parse_mode)
    else:
        await target.answer(parts[0], parse_mode=parse_mode)

    # Остальные части
    for i, part in enumerate(parts[1:], 1):
        if i == len(parts) - 1 and reply_markup:
            if hasattr(target, 'message'):
                await target.message.answer(part, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
                await target.answer(part, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            if hasattr(target, 'message'):
                await target.message.answer(part, parse_mode=parse_mode)
            else:
                await target.answer(part, parse_mode=parse_mode)
        await asyncio.sleep(0.3)


# ---------- МЕНЮ ФИЛЬТРОВ ----------
async def start_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(filters={})
    await show_filters_menu(callback.message, state)


async def show_filters_menu(message: types.Message, state: FSMContext, edit: bool = True):
    data = await state.get_data()
    filters = data.get('filters', {})

    text = "🔍 **Настройка фильтров поиска**\n\n"
    if filters:
        text += "📌 **Выбранные фильтры:**\n"
        for key, val in filters.items():
            if key == 'Тематика':
                text += f"• {key}: {TOPICS.get(val, val)}\n"
            elif key =='title':
                text += f"• Название: {val}\n"
            elif key == 'publication_date_range':
                start_date = val.get('start')
                end_date = val.get('end')
                if start_date and end_date:
                    text += f"• Период публикации: с {start_date} по {end_date}\n"
                elif start_date:
                    text += f"• Период публикации: с {start_date}\n"
                elif end_date:
                    text += f"• Период публикации: по {end_date}\n"
            elif key == 'Этап':
                text += f"• {key}: {STAGE_DESCRIPTIONS.get(val, val)}\n"
            elif key == 'Статус':
                text += f"• {key}: {STATUS_DESCRIPTIONS.get(val, val)}\n"
            else:
                text += f"• {key}: {val}\n"
        text += "\n"
    else:
        text += "Ни один фильтр не выбран.\n\n"

    text += "Выберите фильтры:"

    keyboard = [
        [InlineKeyboardButton(text="🏢 Разработчик", callback_data="filter_developer"),
         InlineKeyboardButton(text="📌 Этап", callback_data="filter_stage")],
        [InlineKeyboardButton(text="🔄 Статус", callback_data="filter_status"),
         InlineKeyboardButton(text="📄 Процедура", callback_data="filter_procedure")],
        [InlineKeyboardButton(text="🏷️ Тематика", callback_data="filter_topic"),
         InlineKeyboardButton(text="📅 Период публикации", callback_data="filter_pubdate")],
         [InlineKeyboardButton(text="📝 Название проекта", callback_data="filter_title")],
        [InlineKeyboardButton(text="✅ Выполнить поиск", callback_data="filter_search_execute"),
        InlineKeyboardButton(text="🗑 Сбросить фильтры", callback_data="filter_reset")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main")]
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if edit:
        await send_long_message(message, text, parse_mode="Markdown", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=markup)
    await state.set_state(SearchStates.waiting_for_filter)


async def filter_reset(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(filters={})
    await callback.answer("Фильтры сброшены")
    await show_filters_menu(callback.message, state)

async def filter_title(callback: types.CallbackQuery, state: FSMContext):
    await send_long_message(
        callback,
        "📝 Введите название проекта (или его часть):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_filters")]
        ])
    )
    await state.set_state(SearchStates.waiting_for_title_filter)
async def process_title_filter(message: types.Message, state: FSMContext):
    title_part = message.text.strip()
    if len(title_part) < 2:
        await message.answer("❌ Введите минимум 2 символа")
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["title"] = title_part   # добавим ключ "Название"
    await state.update_data(filters=filters)
    await show_filters_menu(message, state, edit=False)
# ---------- РАЗРАБОТЧИК (с поиском и пагинацией по 10) ----------
async def filter_developer(callback: types.CallbackQuery, state: FSMContext, db: Database):
    developers = await db.get_unique_developers()
    if not developers:
        await callback.answer("Нет данных о разработчиках", show_alert=True)
        return
    await state.update_data(all_developers=developers, dev_offset=0, dev_filter=None)
    await show_developers_page(callback, state)


async def show_developers_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    all_devs = data.get("all_developers", [])
    dev_filter = data.get("dev_filter")
    offset = data.get("dev_offset", 0)
    page_size = 10

    # Фильтрация
    if dev_filter:
        filtered = [d for d in all_devs if dev_filter.lower() in d.lower()]
    else:
        filtered = all_devs

    chunk = filtered[offset:offset + page_size]
    total = len(filtered)

    keyboard = []
    # Кнопка поиска
    keyboard.append([InlineKeyboardButton(text="🔍 Поиск разработчика", callback_data="developer_search")])
    # Двухколоночный вывод
    for i in range(0, len(chunk), 2):
        row = []
        row.append(InlineKeyboardButton(text=chunk[i], callback_data=f"filter_dev_idx_{offset + i}"))
        if i + 1 < len(chunk):
            row.append(InlineKeyboardButton(text=chunk[i + 1], callback_data=f"filter_dev_idx_{offset + i + 1}"))
        keyboard.append(row)

    # Пагинация
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"dev_page_{max(0, offset - page_size)}"))
    if offset + page_size < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"dev_page_{offset + page_size}"))
    if nav:
        keyboard.append(nav)

    if dev_filter:
        keyboard.append([InlineKeyboardButton(text="❌ Сбросить поиск", callback_data="dev_reset_filter")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад к фильтрам", callback_data="back_to_filters")])

    text = f"🏢 **Выберите разработчика**\nПоказано {len(chunk)} из {total}"
    if dev_filter:
        text += f"\n🔎 Фильтр: «{dev_filter}»"

    await send_long_message(callback, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(SearchStates.waiting_for_filter_value)


async def dev_page_callback(callback: types.CallbackQuery, state: FSMContext):
    offset = int(callback.data.split("_")[2])
    await state.update_data(dev_offset=offset)
    await show_developers_page(callback, state)


async def start_developer_search(callback: types.CallbackQuery, state: FSMContext):
    await send_long_message(
        callback,
        "🔍 **Введите название разработчика** (или его часть)\n\nНапример: *минфин* или *рос*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_developer_list")]
        ])
    )
    await state.set_state(SearchStates.waiting_for_developer_search)


async def process_developer_search(message: types.Message, state: FSMContext, db: Database):
    search_text = message.text.strip()
    if len(search_text) < 2:
        await message.answer("❌ Введите минимум 2 символа для поиска")
        return

    developers = await db.get_unique_developers()
    filtered = [d for d in developers if search_text.lower() in d.lower()]
    await state.update_data(all_developers=developers, dev_filter=search_text, dev_offset=0)

    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
        async def answer(self, *args, **kwargs):
            pass

    await show_developers_page(FakeCallback(message), state)


async def dev_reset_filter(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(dev_filter=None, dev_offset=0)
    await show_developers_page(callback, state)


async def back_to_developer_list(callback: types.CallbackQuery, state: FSMContext):
    await show_developers_page(callback, state)


# ---------- ЭТАП ----------
async def filter_stage(callback: types.CallbackQuery, state: FSMContext):
    stages = [("Не определен", "Не определен")] + list(STAGE_DESCRIPTIONS.items())
    keyboard = []
    for i in range(0, len(stages), 2):
        row = []
        k1, d1 = stages[i]
        cb1 = "filter_stage_val_Не определен" if k1 == "Не определен" else f"filter_stage_val_{k1}"
        row.append(InlineKeyboardButton(text=d1, callback_data=cb1))
        if i+1 < len(stages):
            k2, d2 = stages[i+1]
            cb2 = "filter_stage_val_Не определен" if k2 == "Не определен" else f"filter_stage_val_{k2}"
            row.append(InlineKeyboardButton(text=d2, callback_data=cb2))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_filters")])
    await send_long_message(callback, "📌 **Этап разработки:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(SearchStates.waiting_for_filter_value)


# ---------- СТАТУС ----------
async def filter_status(callback: types.CallbackQuery, state: FSMContext):
    statuses = list(STATUS_DESCRIPTIONS.items())
    keyboard = []
    for i in range(0, len(statuses), 2):
        row = []
        k1, d1 = statuses[i]
        row.append(InlineKeyboardButton(text=d1, callback_data=f"filter_status_val_{k1}"))
        if i+1 < len(statuses):
            k2, d2 = statuses[i+1]
            row.append(InlineKeyboardButton(text=d2, callback_data=f"filter_status_val_{k2}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_filters")])
    await send_long_message(callback, "🔄 **Статус проекта:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(SearchStates.waiting_for_filter_value)


# ---------- ПРОЦЕДУРА ----------
async def filter_procedure(callback: types.CallbackQuery, state: FSMContext):
    procedures = list(PROCEDURE_TYPES.values())
    await state.update_data(temp_procedures_list=procedures)
    keyboard = []
    for i in range(0, len(procedures), 2):
        row = []
        row.append(InlineKeyboardButton(text=procedures[i], callback_data=f"filter_proc_idx_{i}"))
        if i+1 < len(procedures):
            row.append(InlineKeyboardButton(text=procedures[i+1], callback_data=f"filter_proc_idx_{i+1}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_filters")])
    await send_long_message(callback, "📄 **Процедура:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(SearchStates.waiting_for_filter_value)


# ---------- ТЕМАТИКА ----------
async def filter_topic(callback: types.CallbackQuery, state: FSMContext):
    topics_items = list(TOPICS.items())
    await state.update_data(temp_topics_list=topics_items)
    keyboard = []
    for i in range(0, len(topics_items), 2):
        row = []
        k1, d1 = topics_items[i]
        row.append(InlineKeyboardButton(text=d1, callback_data=f"filter_topic_idx_{i}"))
        if i+1 < len(topics_items):
            k2, d2 = topics_items[i+1]
            row.append(InlineKeyboardButton(text=d2, callback_data=f"filter_topic_idx_{i+1}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_filters")])
    await send_long_message(callback, "🏷️ **Тематика:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(SearchStates.waiting_for_filter_value)


# ---------- ПЕРИОД ПУБЛИКАЦИИ ----------
async def filter_pubdate(callback: types.CallbackQuery, state: FSMContext):
    await send_long_message(
        callback,
        "📅 Введите начальную дату (ГГГГ-ММ-ДД) или /пропустить",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="filter_date_skip_start")]
        ])
    )
    await state.set_state(SearchStates.waiting_for_date_start)


async def filter_discussion(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("В разработке", show_alert=True)


# ---------- ОБРАБОТКА ДАТ ----------
async def process_date_start(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if date_str.lower() == "пропустить":
        await state.update_data(temp_date_start=None)
        await message.answer(
            "Введите конечную дату или пропустите:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭ Пропустить", callback_data="filter_date_skip_end")]
            ])
        )
        await state.set_state(SearchStates.waiting_for_date_end)
        return
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        await state.update_data(temp_date_start=date_str)
        await message.answer(
            "Введите конечную дату или пропустите:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏭ Пропустить", callback_data="filter_date_skip_end")]
            ])
        )
        await state.set_state(SearchStates.waiting_for_date_end)
    except ValueError:
        await message.answer("❌ Неверный формат. Пример: 2024-01-01")


async def process_date_end(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    data = await state.get_data()
    start = data.get("temp_date_start")
    if date_str.lower() == "пропустить":
        end = None
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            end = date_str
        except ValueError:
            await message.answer("❌ Неверный формат")
            return
    filters = data.get("filters", {})
    if start or end:
        filters["publication_date_range"] = {"start": start, "end": end}
    else:
        filters.pop("publication_date_range", None)
    await state.update_data(filters=filters, temp_date_start=None)
    await show_filters_menu(message, state, edit=False)


async def filter_date_skip_start(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(temp_date_start=None)
    await send_long_message(
        callback,
        "Введите конечную дату или пропустите:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="filter_date_skip_end")]
        ])
    )
    await state.set_state(SearchStates.waiting_for_date_end)


async def filter_date_skip_end(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    start = data.get("temp_date_start")
    filters = data.get("filters", {})
    if start:
        filters["publication_date_range"] = {"start": start, "end": None}
    else:
        filters.pop("publication_date_range", None)
    await state.update_data(filters=filters, temp_date_start=None)
    await show_filters_menu(callback.message, state)


# ---------- СОХРАНЕНИЕ ВЫБРАННОГО ФИЛЬТРА ----------
async def save_filter_value(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    state_data = await state.get_data()
    filters = state_data.get("filters", {})

    # Разработчик (через индекс)
    if data.startswith("filter_dev_idx_"):
        idx = int(data.split("_")[-1])
        all_devs = state_data.get("all_developers", [])
        dev_filter = state_data.get("dev_filter")
        if dev_filter:
            filtered_devs = [d for d in all_devs if dev_filter.lower() in d.lower()]
        else:
            filtered_devs = all_devs
        if 0 <= idx < len(filtered_devs):
            filters["Разработчик"] = filtered_devs[idx]
            await state.update_data(filters=filters)
            await callback.answer(f"Добавлен: {filtered_devs[idx]}")
            await show_filters_menu(callback.message, state)
        return

    # Процедура (через индекс)
    if data.startswith("filter_proc_idx_"):
        idx = int(data.split("_")[-1])
        procs = state_data.get("temp_procedures_list", [])
        if 0 <= idx < len(procs):
            filters["Процедура"] = procs[idx]
            await state.update_data(filters=filters)
            await callback.answer(f"Добавлена: {procs[idx]}")
            await show_filters_menu(callback.message, state)
        return

    # Тематика (через индекс)
    if data.startswith("filter_topic_idx_"):
        idx = int(data.split("_")[-1])
        topics = state_data.get("temp_topics_list", [])
        if 0 <= idx < len(topics):
            key, desc = topics[idx]
            filters["Тематика"] = key
            await state.update_data(filters=filters)
            await callback.answer(f"Добавлена: {desc}")
            await show_filters_menu(callback.message, state)
        return

    # Этап (прямое значение)
    if data.startswith("filter_stage_val_"):
        value = data.split("_val_")[1]
        filters["Этап"] = value if value != "Не определен" else ""
        await state.update_data(filters=filters)
        await callback.answer(f"Добавлен этап: {STAGE_DESCRIPTIONS.get(value, value)}")
        await show_filters_menu(callback.message, state)
        return

    # Статус (прямое значение)
    if data.startswith("filter_status_val_"):
        value = data.split("_val_")[1]
        filters["Статус"] = value
        await state.update_data(filters=filters)
        await callback.answer(f"Добавлен статус: {STATUS_DESCRIPTIONS.get(value, value)}")
        await show_filters_menu(callback.message, state)
        return

    await callback.answer("Неизвестный фильтр", show_alert=True)


# ---------- ВЫПОЛНЕНИЕ ПОИСКА ----------
async def filter_search_execute(callback: types.CallbackQuery, state: FSMContext, db: Database):
    data = await state.get_data()
    filters = data.get("filters", {})
    if not filters:
        await callback.answer("Выберите хотя бы один фильтр", show_alert=True)
        return
    projects = await db.search_projects_with_filters(filters)
    if not projects:
        await send_long_message(
            callback,
            "❌ По заданным фильтрам ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_filters")]
            ])
        )
        return
    await state.update_data(search_results=projects, search_query="фильтры", page=0)
    await send_search_results(callback, projects, "фильтры", 0, state)


async def back_to_filters(callback: types.CallbackQuery, state: FSMContext):
    await show_filters_menu(callback.message, state)


# ---------- ОБЫЧНЫЙ ПОИСК ПО ТЕКСТУ ----------
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    from main import get_main_menu_keyboard
    await send_long_message(callback, "📋 Главное меню", reply_markup=get_main_menu_keyboard())


async def process_search_query(message: types.Message, state: FSMContext, db: Database):
    query = message.text.strip()
    if len(query) < 3:
        await message.answer("❌ Минимум 3 символа")
        return
    projects = await search_in_db(db, query)
    if not projects:
        await message.answer(f"По запросу «{query}» ничего не найдено")
        return
    await send_search_results_as_message(message, projects, query, state)


# ---------- ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ ----------
async def send_search_results_as_message(message: types.Message, projects, query, state, per_page=10):
    total = len(projects)
    start = 0
    end = min(per_page, total)
    chunk = projects[start:end]

    text = f"🔍 Результаты по запросу: {query}\n📊 Найдено: {total}\n\n"
    for idx, p in enumerate(chunk, 1):
        title = p.get('title', 'Без названия')
        dept = p.get('developedDepartment', {}).get('description', 'Не указано')
        date = p.get('publicationDate', '') or p.get('creationDate', '')
        date_str = date[:10] if date else 'Дата не указана'
        proj_id = p.get('id')
        text += f"{idx}. **{title}**\n\n\n   🏢 {dept}\n\n\n   📅 {date_str}\n\n\n   🔗 https://regulation.gov.ru/projects#npa={proj_id}\n\n"

    keyboard = []
    if total > per_page:
        keyboard.append([InlineKeyboardButton(text="Вперёд ▶️", callback_data="search_page|1")])
    keyboard.append([
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search_start"),
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_main")
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await send_long_message(message, text, parse_mode="Markdown", reply_markup=markup)
    await state.update_data(search_results=projects, search_query=query, page=0)


async def send_search_results(callback: types.CallbackQuery, projects, query, page, state, per_page=10):
    """
    Отправляет результаты поиска с кнопками добавления для каждого проекта.
    """
    total = len(projects)
    start = page * per_page
    end = min(start + per_page, total)
    chunk = projects[start:end]

    # Формируем заголовок в зависимости от типа поиска
    if query == "фильтры":
        data = await state.get_data()
        filters = data.get("filters", {})
        lines = []
        for k, v in filters.items():
            if k == "Тематика":
                lines.append(f"• {k}: {TOPICS.get(v, v)}")
            elif k == "Этап":
                lines.append(f"• {k}: {STAGE_DESCRIPTIONS.get(v, v)}")
            elif k == "Статус":
                lines.append(f"• {k}: {STATUS_DESCRIPTIONS.get(v, v)}")
            elif k == "publication_date_range":
                start_date = v.get('start')
                end_date = v.get('end')
                if start_date and end_date:
                    lines.append(f"• Период публикации: с {start_date} по {end_date}")
                elif start_date:
                    lines.append(f"• Период публикации: с {start_date}")
                elif end_date:
                    lines.append(f"• Период публикации: по {end_date}")
            else:
                lines.append(f"• {k}: {v}")
        filters_str = "\n".join(lines) if lines else "нет"
        header = f"🔍 Результаты по фильтрам:\n{filters_str}\n"
    else:
        header = f"🔍 Результаты по запросу: {query}\n"

    text = header + f"📊 Найдено: {total}\n📄 Показано {start+1}-{end}\n\n"

    # Добавляем описание каждого проекта
    for idx, p in enumerate(chunk, start=1):
        title = p.get('title', 'Без названия')
        dept = p.get('developedDepartment', {}).get('description', 'Не указано')
        date = p.get('publicationDate', '') or p.get('creationDate', '')
        date_str = date[:10] if date else 'Дата не указана'
        proj_id = p.get('id')
        text += (f"{idx}. **{title}**\n"
                 f"   🏢 {dept}\n"
                 f"   📅 {date_str}\n"
                 f"   🔗 [Ссылка](https://regulation.gov.ru/projects#npa={proj_id})\n\n")

    # Построение inline-клавиатуры
    keyboard = []

    # Кнопки добавления для каждого проекта на отдельной строке
    for idx, p in enumerate(chunk, start=1):
        proj_id = p.get('id')
        title_short = p.get('title', 'Проект')[:30]  # обрезаем длинные названия
        keyboard.append([InlineKeyboardButton(
            text=f"⭐ Добавить:{idx}. {title_short}",
            callback_data=f"add_fav_{proj_id}"
        )])

    # Пагинация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"search_page|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"search_page|{page+1}"))
    if nav:
        keyboard.append(nav)

    # Кнопки управления
    keyboard.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search_start")])
    keyboard.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_main")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    # Отправляем сообщение (с возможным разбиением на части)
    await send_long_message(callback, text, parse_mode="Markdown", reply_markup=markup)

    # Сохраняем данные в состоянии для пагинации
    await state.update_data(search_results=projects, search_query=query, page=page)


def _format_filter_value(key, value):
    if key == "Тематика":
        return TOPICS.get(value, value)
    if key == "Этап":
        return STAGE_DESCRIPTIONS.get(value, value)
    if key == "Статус":
        return STATUS_DESCRIPTIONS.get(value, value)
    return value


async def search_in_db(db: Database, search_text: str) -> list:
    pattern = f"%{search_text}%"
    query = """
        SELECT external_id as id, title, department, creation_date, publication_date, raw_json, topics, stages_info
        FROM projects
        WHERE title ILIKE $1 OR department ILIKE $1 OR raw_json->>'description' ILIKE $1
        ORDER BY publication_date DESC NULLS LAST LIMIT 10000
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, pattern)
    projects = []
    for row in rows:
        raw = row['raw_json']
        if isinstance(raw, str):
            import json
            raw = json.loads(raw)
        topics_val = row['topics']
        if isinstance(topics_val, str):
            topics_val = json.loads(topics_val)
        projects.append({
            'id': row['id'],
            'title': row['title'],
            'developedDepartment': {'description': row['department']} if row['department'] else None,
            'creationDate': row['creation_date'].isoformat() if row['creation_date'] else None,
            'publicationDate': row['publication_date'].isoformat() if row['publication_date'] else None,
            'raw_json': raw,
            'classified_topics': topics_val or [],
            'stages_info': row['stages_info'] or ''
        })
    return projects