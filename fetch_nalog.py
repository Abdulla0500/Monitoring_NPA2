import requests
from bs4 import BeautifulSoup
import time
import json

BASE_URL = 'https://www.nalog.gov.ru'
START_URL = '/rn77/about_fts/docs_fts/'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.nalog.gov.ru/',
}

def get_last_page_number(url):
    resp = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'html.parser')
    last_link = soup.find('a', class_='pagination__side', string='в конец')
    if last_link and last_link.get('href'):
        last_page_str = last_link['href'].split('/')[-1].replace('.html', '')
        return int(last_page_str)
    all_pages = soup.find_all('a', class_='pagination_desktop')
    if all_pages:
        last_num = all_pages[-1].text.strip()
        return int(last_num)
    return 1

def parse_documents_from_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', class_='news-block__item')
    result = []
    for item in items:
        a_tag = item.find('a')
        if not a_tag:
            continue
        href = a_tag.get('href')
        full_url = BASE_URL + href if href.startswith('/') else href

        p_tag = a_tag.find('p')
        title = p_tag.get_text(strip=True) if p_tag else ''
        for p in a_tag.find_all('p'):
            p.extract()
        short_desc = a_tag.get_text(strip=True)

        # Ищем тип документа: берём непустой и не скрытый
        type_tags = item.find_all('div', class_='tags__item_noactive')
        doc_type = ''
        for tag in type_tags:
            text = tag.get_text(strip=True)
            if text and tag.get('style', '').find('display: none') == -1:
                doc_type = text
                break

        result.append({
            'url': full_url,
            'short_description': short_desc,
            'title': title,
            'type': doc_type
        })
    return result

def parse_all_pages():
    first_page_url = BASE_URL + START_URL
    last_page = get_last_page_number(first_page_url)
    print(f'Найдено страниц: {last_page}')

    all_docs = []
    for page_num in range(1, last_page + 1):
        if page_num == 1:
            url = first_page_url
        else:
            url = f'{BASE_URL}{START_URL}{page_num}.html'
        print(f'Загружаем страницу {page_num} из {last_page}...')
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f'Ошибка {resp.status_code} на странице {page_num}, пропускаем')
                continue
            docs = parse_documents_from_page(resp.text)
            all_docs.extend(docs)
            print(f'  -> найдено {len(docs)} документов, всего {len(all_docs)}')
            time.sleep(0.5)
        except Exception as e:
            print(f'Ошибка при загрузке страницы {page_num}: {e}')
            continue

    return all_docs

if __name__ == '__main__':
    documents = parse_all_pages()
    print(f'Всего собрано документов: {len(documents)}')
    with open('nalog_docs.json', 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    print('Готово! Данные сохранены в nalog_docs.json')
    print("\n=== Пример собранных данных (первые 5 документов) ===\n")
    for i, doc in enumerate(documents[:5], 1):
        print(f"{i}. {doc['short_description']}")
        print(f"   Ссылка: {doc['url']}")
        print(f"   Полное название: {doc['title'][:100]}...")
        print(f"   Тип: {doc['type']}\n")