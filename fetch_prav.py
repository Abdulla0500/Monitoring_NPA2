import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin

BASE_URL = "http://publication.pravo.gov.ru"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def parse_page(url):
    """Парсит страницу со списком документов и возвращает список словарей."""
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Ошибка загрузки: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    # Все строки с документами
    rows = soup.select('div.documents-table-row')
    result = []

    for row in rows:
        # 1. Порядковый номер
        num_cell = row.find('div', class_='documents-item-number')
        number = num_cell.text.strip() if num_cell else ''

        # 2. Основной блок с содержимым
        fill_cell = row.find('div', class_='documents-fill')
        if not fill_cell:
            continue

        # 3. Ссылка и название документа
        name_link = fill_cell.find('a', class_='documents-item-name')
        if name_link:
            doc_url = urljoin(BASE_URL, name_link.get('href'))
            # Получаем текст, заменяя <br> на пробелы
            title = ' '.join(name_link.stripped_strings)  # учитывает все текстовые фрагменты
        else:
            doc_url = None
            title = ''

        # 4. Блок информации (номер опубликования, дата, PDF)
        info_div = fill_cell.find('div', class_='infoindocumentlist')
        pub_number = ''
        pub_date = ''
        pdf_link = ''
        pdf_size = ''

        if info_div:
            # Ищем все элементы с информацией
            for item in info_div.find_all('div'):
                label_span = item.find('span', class_='info-name')
                data_span = item.find('span', class_='info-data')
                if label_span and data_span:
                    label_text = label_span.text.strip()
                    if 'Номер опубликования' in label_text:
                        pub_number = data_span.text.strip()
                    elif 'Дата опубликования' in label_text:
                        pub_date = data_span.text.strip()

                # Ссылка на PDF
                pdf_a = item.find('a', class_='documents-item-file')
                if pdf_a:
                    pdf_link = urljoin(BASE_URL, pdf_a.get('href'))
                    size_span = pdf_a.find('span', class_='documents-pdf-downloadlink')
                    if size_span:
                        pdf_size = size_span.text.strip()

        result.append({
            'number': number,
            'title': title,
            'doc_url': doc_url,
            'pub_number': pub_number,
            'pub_date': pub_date,
            'pdf_link': pdf_link,
            'pdf_size': pdf_size,
        })

    return result


if __name__ == "__main__":
    url = "http://publication.pravo.gov.ru/documents/daily"
    print(f"Парсим {url}")
    documents = parse_page(url)

    if not documents:
        print("Документы не найдены.")
    else:
        print(f"Собрано {len(documents)} документов")
        with open("pravo_daily.json", "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
        print("Результат сохранён в pravo_daily.json")