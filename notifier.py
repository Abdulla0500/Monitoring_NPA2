import asyncio
from datetime import datetime, timedelta
from database import Database
from roles import format_project_analyst,format_project_lawyer,format_project_product 

async def send_daily_notifications(bot):
    db = Database()
    await db.connect()
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    users = await db.get_users_by_notification_time(current_time_str)
    
    if now.weekday() == 0:  
        dates = [
            (now - timedelta(days=3)).date(),
            (now - timedelta(days=2)).date(),
            (now - timedelta(days=1)).date()
        ]
    else:
        dates = [(now - timedelta(days=1)).date()]
    
    for user in users:
        user_id_db = user['user_id']
        tg_id = user['telegram_id']
        role = user['role']
        projects = []
        for d in dates:
            projs = await db.get_projects_by_date(user_id_db, d)
            projects.extend(projs)
        # дедупликация по id
        unique = {}
        for p in projects:
            unique[p['id']] = p
        projects = list(unique.values())
        
        if projects:
            text = format_digest(projects, dates, role)
            await bot.send_message(tg_id, text, parse_mode='Markdown')
            # Помечаем каждый проект отправленным
            for p in projects:
                await db.mark_notification_sent(user_id_db, p['id'])
        else:
            text = format_no_projects(dates)
            await bot.send_message(tg_id, text, parse_mode='Markdown')
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
        else:  # product
            body += f"{i}. {format_project_product(p)}\n"
        body += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    footer = "\n🔔 *Ваши подписки:* "

    
    return header + body + footer


def format_no_projects(dates):

    if len(dates) == 1:
        return f"📅 *За {dates[0].strftime('%d.%m.%Y')} новых проектов по вашим темам не найдено.*\n\nВы получите уведомление, как только появятся новые проекты."
    else:
        start_str = min(dates).strftime('%d.%m')
        end_str = max(dates).strftime('%d.%m.%Y')
        return f"📅 *За период {start_str}–{end_str} новых проектов по вашим темам не найдено.*\n\nВы получите уведомление, как только появятся новые проекты."