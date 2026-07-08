import requests
from bs4 import BeautifulSoup
import time
import json  
from urllib.parse import urljoin

BASE_URL = "https://sfr.gov.ru/press_center/news/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def parse_page(url):
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.select('article.re-news__article')
    result = []
    for article in articles:
        link_tag = article.find('a', class_='re-news__article-link')
        if link_tag:
            href = link_tag.get('href')
            full_url = urljoin(BASE_URL, href) if href else None
        else:
            full_url = None
        title_tag = article.find('h3', class_='re-news__article-title')
        title = title_tag.text.strip() if title_tag else ''
        desc_tag=article.find('p',class_='re-news__article-description')
        description = desc_tag.text.strip() if desc_tag else ''
        time_tag = article.find('time')
        if time_tag:
            datetime_str = time_tag.get('datetime')
            date_span = time_tag.find('span', class_='date')
            time_span = time_tag.find('span', class_='time')
            date_text = date_span.text.strip() if date_span else ''
            time_text = time_span.text.strip() if time_span else ''
        else:
            datetime_str = date_text = time_text = None
        result.append({
            'title': title,
            'url': full_url,
            'datetime': datetime_str,
            'date': date_text,
            'time': time_text,
            'description': description
        })

    return result

# Собираем новости (первые 5 страниц – измените на 5323 для полного сбора)
all_news = []
for page in range(1, 6):
    if page == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}page{page}/"
    print(f"Парсим {url}")
    news = parse_page(url)
    if not news:
        break
    all_news.extend(news)
    time.sleep(1)

print(f"Собрано {len(all_news)} новостей")

# Сохраняем в JSON-файл
with open("news_sfr.json", "w", encoding="utf-8") as f:
    json.dump(all_news, f, ensure_ascii=False, indent=2)

print("Результат сохранён в news_sfr.json")