import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urljoin

BASE_URL = "https://gnivc.ru"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def parse_templates():
    url = "https://gnivc.ru/software-and-services/form-templates/"
    resp = requests.get(url, headers=HEADERS)
    resp.encoding = 'utf-8'  # добавляем
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    container = soup.find('div', class_=lambda c: c and 'ExpandableList-module__expandableList' in c)
    if not container:
        container = soup.find('div', class_=re.compile(r'expandableList'))
    if not container:
        print("Не найден контейнер списка")
        return []

    titles = container.select('[class*="titleWrapper"]')
    contents = container.select('[class*="content"]')
    
    if len(titles) != len(contents):
        print(f"Несоответствие: {len(titles)} заголовков, {len(contents)} контентов")
        count = min(len(titles), len(contents))
        titles = titles[:count]
        contents = contents[:count]

    groups = []
    for title_elem, content_elem in zip(titles, contents):
        title_h3 = title_elem.find('h3')
        group_title = title_h3.text.strip() if title_h3 else ''
        if not group_title:
            continue

        date_div = content_elem.find('div', class_=lambda c: c and 'date' in c)
        release_date = date_div.text.replace('Дата релиза:', '').strip() if date_div else ''

        doc_list = content_elem.find('div', class_=lambda c: c and 'documentList' in c)
        doc_links = []
        if doc_list:
            for a in doc_list.find_all('a'):
                href = a.get('href')
                if href:
                    full_url = urljoin(BASE_URL, href)
                    # Извлекаем только прямые текстовые узлы, игнорируя SVG
                    text_parts = [part.strip() for part in a.contents if isinstance(part, str)]
                    file_name = ' '.join(text_parts).strip() if text_parts else ''
                    # Fallback на случай, если структура иная
                    if not file_name:
                        file_name = a.get_text(strip=True)
                        if 'Created with Pixso.' in file_name:
                            file_name = file_name.replace('Created with Pixso.', '').strip()
                    doc_links.append({
                        'name': file_name,
                        'url': full_url
                    })

        releases_wrapper = content_elem.find('div', class_=lambda c: c and 'Releases-module__wrapper' in c)
        updates = []
        if releases_wrapper:
            for item in releases_wrapper.find_all('div', class_=lambda c: c and 'releaseItem' in c):
                link_tag = item.find('a')
                if link_tag:
                    href = link_tag.get('href')
                    full_url = urljoin(BASE_URL, href) if href else None
                    # Аналогично для имён в релизах
                    text_parts = [part.strip() for part in link_tag.contents if isinstance(part, str)]
                    name = ' '.join(text_parts).strip() if text_parts else link_tag.get_text(strip=True)
                    if 'Created with Pixso.' in name:
                        name = name.replace('Created with Pixso.', '').strip()
                else:
                    full_url = None
                    name = ''
                desc_div = item.find('div', class_=lambda c: c and 'description' in c)
                description = desc_div.text.strip() if desc_div else ''
                updates.append({
                    'name': name,
                    'url': full_url,
                    'description': description
                })

        groups.append({
            'title': group_title,
            'release_date': release_date,
            'documents': doc_links,
            'updates': updates
        })

    return groups


if __name__ == "__main__":
    data = parse_templates()
    if data:
        print(f"Собрано {len(data)} групп шаблонов")
        with open("gnivc_templates.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Результат сохранён в gnivc_templates.json")
    else:
        print("Ничего не найдено.")