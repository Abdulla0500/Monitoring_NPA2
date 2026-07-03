import requests
from bs4 import BeautifulSoup
import time
import json  # <-- добавили модуль json

BASE_URL = "https://buh.ru/news/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def parse_page(url):
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("a.news_item__link")
    result = []
    for item in items:
        link = item.get("href")
        if not link:
            continue
        if not link.startswith("http"):
            link = "https://buh.ru" + link
        title_div = item.select_one(".news_item__title")
        if title_div:
            title = title_div.get_text(strip=True)
            # теперь добавляем словарь, а не кортеж
            result.append({"title": title, "link": link})
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
with open("news.json", "w", encoding="utf-8") as f:
    json.dump(all_news, f, ensure_ascii=False, indent=2)

print("Результат сохранён в news.json")