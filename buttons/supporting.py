import asyncio
import logging
logger = logging.getLogger(__name__)
from fetcher import RegulationAPI 
from datetime import datetime
from Dictionaries import PROJECT_TYPES, STAGE_DESCRIPTIONS,STATUS_DESCRIPTIONS,PROCEDURE_TYPES
api = RegulationAPI()
async def fetch_with_retry_simple(fetch_func, max_retries=3, delay=2, *args, **kwargs):

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Попытка {attempt} из {max_retries}")
            result = await fetch_func(*args, **kwargs)
            if result:
                logger.info(f"Успешно на попытке {attempt}")
                return result
            else:
                logger.warning(f"Попытка {attempt} вернула пустой результат")
        except Exception as e:
            logger.error(f"Ошибка на попытке {attempt}: {e}")
        if attempt < max_retries:
            wait_time = delay * attempt
            logger.info(f"Ждем {wait_time} секунд...")
            await asyncio.sleep(wait_time)
    logger.error(f"Все {max_retries} попыток провалились")
    return None

async def split_long_message_for_query(query, text, parse_mode='Markdown', reply_markup=None,
                                       chunk_size: int = 4096):
    if len(text) <= chunk_size:
        try:
            return await query.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return await query.message.edit_text(text, reply_markup=reply_markup)

    parts = []
    current_part = ""
    for line in text.split('\n'):
        if len(current_part) + len(line) + 1 <= chunk_size:
            if current_part:
                current_part += '\n' + line
            else:
                current_part = line
        else:
            if current_part:
                parts.append(current_part)
            current_part = line
    if current_part:
        parts.append(current_part)

    try:
        await query.message.edit_text(parts[0], parse_mode=parse_mode)
    except Exception as e:
        await query.message.edit_text(parts[0])

    for i, part in enumerate(parts[1:], 1):
        try:
            if i == len(parts) - 1 and reply_markup:
                await query.message.answer(part, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
                await query.message.answer(part, parse_mode=parse_mode)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Error sending part {i}: {e}")

    return None

def format_project_stage(project):
    stage = project.get('stage', '')
    status = project.get('status', '')
    procedure = project.get('procedure', {})
    project_type = project.get('projectType', {})
    stage_text = []

    if project_type and project_type.get('id'):
        type_desc = PROJECT_TYPES.get(project_type.get('id'), project_type.get('description', 'Неизвестный тип'))
        stage_text.append(f"📌 **Тип:** {type_desc}")

    if stage:
        stage_desc = STAGE_DESCRIPTIONS.get(stage, stage)
        stage_text.append(f"\n📍 **Этап:** {stage_desc}")

    if status:
        status_desc = STATUS_DESCRIPTIONS.get(status, status)
        stage_text.append(f"\n⚡ **Статус:** {status_desc}")

    if procedure and procedure.get('id'):
        proc_desc = PROCEDURE_TYPES.get(procedure.get('id'), procedure.get('description', 'Неизвестная процедура'))
        stage_text.append(f"\n🔄 **Процедура:** {proc_desc}")

    return "\n".join(stage_text)

async def format_project_stages_detailed(project_id: str) -> str:
    try:
        stages = await fetch_with_retry_simple(
            api.fetch_project_stages,
            max_retries=2,
            delay=1,
            project_id=project_id
        )

        if not stages:
            return "❌ Информация об этапах не найдена"

        text = "📊 **ДЕТАЛЬНАЯ ИНФОРМАЦИЯ ПО ЭТАПАМ**\n\n"

        for stage in stages:
            title = stage.get('title', 'Этап')
            
            text += f"**{title}**\n"

            if stage.get('isCurrent'):
                text += "└ 🔴 **Текущий этап**\n"
            if stage.get('isCompleted'):
                text += "└ ✅ **Завершен**\n"

            if stage.get('file'):
                file = stage['file']
                text += f"└ 📄 **Файл:** {file.get('name', 'Без названия')}\n"
                if file.get('date'):
                    text += f"└ 📅 Дата: {file['date'][:10]}\n"
                if file.get('url'):
                    text += f"└ 🔗 [Скачать]({file['url']})\n"


            if stage.get('modifiedFile'):
                mfile = stage['modifiedFile']
                text += f"└ 📝 **Измененный файл:** {mfile.get('name', 'Без названия')}\n"
                if mfile.get('date'):
                    text += f"└ 📅 Дата изменения: {mfile['date'][:10]}\n"
                if mfile.get('url'):
                    text += f"└ 🔗 [Скачать]({mfile['url']})\n"

            if stage.get('documents'):
                text += f"└ 📑 Документов: {len(stage['documents'])}\n"

            if stage.get('vote'):
                vote = stage['vote']
                text += f"└ 🗳 **Голосование:**\n"
                text += f"  └ За: {vote.get('for', 0)}, Против: {vote.get('against', 0)}\n"
                if vote.get('endDate'):
                    text += f"  └ Завершается: {vote['endDate'][:10]}\n"

            text += "\n" + "─" * 40 + "\n\n"

        return text

    except Exception as e:
        logger.error(f"Ошибка получения этапов для проекта {project_id}: {e}")
        return f"❌ Ошибка загрузки этапов: {e}"

def make_json_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(i) for i in obj]
    elif isinstance(obj, set):
         return [make_json_serializable(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj