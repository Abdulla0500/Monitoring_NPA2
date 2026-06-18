
from Dictionaries import PROJECT_TYPES, PROCEDURE_TYPES, STAGE_DESCRIPTIONS, STATUS_DESCRIPTIONS, TOPICS_SHORT, TOPICS
def format_project_by_role(project, role):
    if role == 'analyst':
        return format_project_analyst(project)
    elif role == 'lawyer':
        return format_project_lawyer(project)
    elif role == 'product':
        return format_project_product(project)
    return format_project_analyst(project)


def format_project_analyst(project):
    title = project.get("title", "Без названия")
    department = project.get("developedDepartment", {}).get("description", "Не указано")
    project_type_id = project.get("projectType", {}).get("id", "")
    project_type = PROJECT_TYPES.get(project_type_id, project.get("projectType", {}).get("description", ""))
    procedure_id = project.get("procedure", {}).get("id", "")
    procedure = PROCEDURE_TYPES.get(procedure_id, project.get("procedure", {}).get("description", ""))
    stage = project.get("stage", "")
    stage_ru = STAGE_DESCRIPTIONS.get(stage, stage)
    status = project.get("status", "")
    status_ru = STATUS_DESCRIPTIONS.get(status, status)
    pub_date = project.get("publicationDate") or project.get("creationDate")
    project_id = project.get("id")
    topics = project.get("classified_topics", [])
    last_modified = project.get("last_modified")
    last_modified_str = f"\n\n📅 *Последнее изменение:* {last_modified}" if last_modified else ""
    if topics:
        topic_labels = [TOPICS_SHORT.get(t, t) for t in topics]
        topic_str = "| ".join(topic_labels)
    else:
        topic_str = "Не определено"

    if pub_date:
        pub_date = pub_date[:10]

    url = f"https://regulation.gov.ru/projects#npa={project_id}"

    text = (
        f"{topic_str}\n\n"
        f"🏢 {department}\n\n"
        f"📂 {project_type}\n\n"
        f"⚖ {procedure}\n\n"
        f"📍 Стадия: {stage_ru}\n\n"
        f"🔄 Статус: {status_ru}\n\n"
        f"📅 Дата публикации: {pub_date}{last_modified_str}\n\n"
        f"📌 {title}\n\n"
        f"🔗 {url}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    return text

def format_project_lawyer(project):
    title = project.get("title", "Без названия")
    project_number = project.get("projectId", "Не указан")
    department = project.get("developedDepartment", {}).get("description", "Не указано")

    project_type_id = project.get("projectType", {}).get("id", "")
    project_type = PROJECT_TYPES.get(
        project_type_id,
        project.get("projectType", {}).get("description", "Не указано")
    )

    procedure_id = project.get("procedure", {}).get("id", "")
    procedure = PROCEDURE_TYPES.get(
        procedure_id,
        project.get("procedure", {}).get("description", "Не указано")
    )

    stage = project.get("stage", "Не указано")
    stage_ru = STAGE_DESCRIPTIONS.get(stage, stage)

    status = project.get("status", "Не указано")
    status_ru = STATUS_DESCRIPTIONS.get(status, status)

    pub_date = project.get("publicationDate") or project.get("creationDate")
    project_id = project.get("id")

    topics = project.get("classified_topics", [])
    last_modified = project.get("last_modified")

    if topics:
        topic_labels = [TOPICS.get(t, t) for t in topics]
        topic_str = ", ".join(topic_labels)
    else:
        topic_str = "НПА"

    if pub_date:
        pub_date = pub_date[:10]

    # Последнее изменение
    last_modified_str = (
        f"\n\n📅 *Последнее изменение:* {last_modified}"
        if last_modified else ""
    )

    stages_text = ""
    if project.get('stages'):
        stages = project['stages']
        stages_text = "\n\n📊 **Этапы проекта:**\n"
        for s in stages:
            title_stage = s.get('title', '')
            is_current = s.get('isCurrent', False)
            if is_current:
                stages_text += f"└ 🔴 **{title_stage}** (текущий)\n"
            else:
                stages_text += f"└ {title_stage}\n"

    url = f"https://regulation.gov.ru/projects#npa={project_id}"

    text = (
        "📄 НОРМАТИВНЫЙ ПРОЕКТ\n\n"
        f"📌 Наименование: {title}\n\n"
        f"🆔 Номер проекта: {project_number}\n\n"
        f"🏢 Разработчик: {department}\n\n"
        f"🧭 Тематика: {topic_str}\n\n"
        f"📂 Тип акта: {project_type}\n\n"
        f"⚖  Процедура: {procedure}\n\n"
        f"📍 Стадия: {stage_ru}\n\n"
        f"🔄 Статус: {status_ru}"
        f"{stages_text}\n\n"
        f"📅 Дата публикации: {pub_date}"
        f"{last_modified_str}\n\n"
        f"🔗 {url}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    return text

def format_project_product(project):
    title = project.get("title", "Без названия")
    department = project.get("developedDepartment", {}).get("description", "Не указано")
    project_type_id = project.get("projectType", {}).get("id", "")
    project_type = PROJECT_TYPES.get(project_type_id, project.get("projectType", {}).get("description", "Не указано"))
    procedure_id = project.get("procedure", {}).get("id", "")
    procedure = PROCEDURE_TYPES.get(procedure_id, project.get("procedure", {}).get("description", "Не указано"))
    status = project.get("status", "Не указано")
    status_ru = STATUS_DESCRIPTIONS.get(status, status)
    project_id = project.get("id")
    topics = project.get("classified_topics", [])
    pub_date = project.get("publicationDate") or project.get("creationDate")
    last_modified = project.get("last_modified")
    last_modified_str = f"\n\n📅 *Последнее изменение:* {last_modified}" if last_modified else ""
    if topics:
        topic_labels = [TOPICS_SHORT.get(t, t) for t in topics]
        topic_str = " | ".join(topic_labels)
    else:
        topic_str = "НПА"

    if pub_date:
        pub_date = pub_date[:10]

    short_title = title
    if len(title) > 120:
        short_title = title[:117] + "..."

    url = f"https://regulation.gov.ru/projects#npa={project_id}"

    text = (
        f"🧭 {topic_str}\n\n"
        f"🏢 {department} | {status_ru} | {pub_date}|{last_modified_str}\n\n"
        f"📌 {short_title}\n\n"
        f"📂 {project_type}\n\n"
        f"⚖ {procedure}\n\n"
        f"🔗 {url}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )

    return text
