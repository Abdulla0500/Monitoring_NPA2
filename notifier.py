import asyncio
from datetime import datetime, timedelta
import holidays
from database import Database
from roles import format_project_analyst, format_project_lawyer, format_project_product


async def send_daily_notifications(bot):
    db = Database()
    await db.connect()
    now = datetime.now()
    today = now.date()

    ru_holidays = holidays.Russia()
    if today in ru_holidays or now.weekday() in (5, 6):
        await db.close()
        return

    current_time_str = now.strftime("%H:%M")
    users = await db.get_users_by_notification_time(current_time_str)

    for user in users:
        user_id_db = user['user_id']
        tg_id = user['telegram_id']
        role = user['role']

        last_date = user.get('last_notification_date')
        if last_date is None:
            await db.update_user_last_date(user_id_db, today - timedelta(days=1))
            continue

        start_date = last_date + timedelta(days=1)
        end_date = today - timedelta(days=1)

        if start_date > end_date:
            await db.update_user_last_date(user_id_db, today)
            continue

        projects = []
        cur = start_date
        while cur <= end_date:
            projs = await db.get_projects_by_date(user_id_db, cur)
            projects.extend(projs)
            cur += timedelta(days=1)

        date_list = [start_date + timedelta(days=i)
                     for i in range((end_date - start_date).days + 1)]

        if projects:
            text = format_digest(projects, date_list, role)
            await bot.send_message(tg_id, text, parse_mode='Markdown')
            for p in projects:
                await db.mark_notification_sent(user_id_db, p['id'])
        else:
            text = format_no_projects(date_list)
            await bot.send_message(tg_id, text, parse_mode='Markdown')

        await db.update_user_last_date(user_id_db, today)
        await asyncio.sleep(0.3)

    await db.close()


def format_digest(projects, dates, role):
    if len(dates) == 1:
        header = f"📅 *Проекты за {dates[0].strftime('%d.%m.%Y')}*\n\n"
    else:
        start_str = min(dates).strftime('%d.%m')
        end_str = max(dates).strftime('%d.%m.%Y')
        header = f"📅 *Дайджест за {start_str}–{end_str}*\n\n"

    header += f"📊 Найдено проектов: *{len(projects)}*\n"
    header += "━━━━━━━━━━━━━━━━━━\n\n"

    body = ""
    for i, p in enumerate(projects, 1):
        if role == 'analyst':
            body += f"{i}. {format_project_analyst(p)}\n"
        elif role == 'lawyer':
            body += f"{i}. {format_project_lawyer(p)}\n"
        else:
            body += f"{i}. {format_project_product(p)}\n"
        body += "━━━━━━━━━━━━━━━━━━━━\n\n"
    return header + body


def format_no_projects(dates):
    if len(dates) == 1:
        return (f"📅 *За {dates[0].strftime('%d.%m.%Y')} новых проектов "
                f"по вашим темам не найдено.*\n\n"
                f"Вы получите уведомление, как только появятся новые проекты.")
    else:
        start_str = min(dates).strftime('%d.%m')
        end_str = max(dates).strftime('%d.%m.%Y')
        return (f"📅 *За период {start_str}–{end_str} новых проектов "
                f"по вашим темам не найдено.*\n\n"
                f"Вы получите уведомление, как только появятся новые проекты.")
    
