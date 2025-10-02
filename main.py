import json
from pathlib import Path
import hashlib
import time
import datetime

from constants import (
    RSS_LINKS, 
    FILTER_BY_TITLE_AND_CONTENT_PROMPT,
    FILTER_BY_TEXT_PROMPT,
    FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER,
    FEEDS_COUNT_CONFUSED,
    API_KEY,
    ALERTS_FOLDER,
    CONTENTS_FOLDER,
    RESPONSES_1_FOLDER,
    RESPONSES_2_FOLDER,
    FINAL_FOLDER,
)

import feedparser
import tiktoken
import tqdm
from google import genai
from google.genai import types
import trafilatura
import justext
from bs4 import BeautifulSoup

# safari selenium
from selenium import webdriver


def get_and_clean_html(driver: webdriver.Safari, link: str) -> str:
    """ clean html here. if fallbacks:
    trafilatura -> justext -> bs4 -> raw html"""
    driver.get(link)
    html = driver.page_source
    # html = trafilatura.fetch_url(link)
    
    try:
        return str(trafilatura.extract(html, favor_recall=True))
    except Exception as e:
        print(f"Error cleaning html with trafilatura: {e}")
    
    try:
        return str(justext.justext(html, justext.get_stoplist("English")))
    except Exception as e:
        print(f"Error cleaning html with jusText: {e}")
    
    try:
        return str(BeautifulSoup(html, "html.parser").get_text())
    except Exception as e:
        print(f"Error cleaning html with bs4: {e}")
    
    return html


def get_alert_by_id(alert_id) -> dict:
    for feed_path in ALERTS_FOLDER.glob("*.json"):
        alert = json.loads(feed_path.read_text())
        for alert in alert:
            if alert["id"] == alert_id:
                return alert
    raise ValueError(f"Alert with id {alert_id} not found")


def get_now_or_latest_file_in_folder(now: int, folder: Path) -> Path:
    if (folder / f"{now}.json").exists():
        return folder / f"{now}.json"
    return max(folder.glob("*.json"), key=lambda x: x.stat().st_mtime)


def main():
    
    now = int(datetime.datetime.now().timestamp())
    ALERTS_FOLDER.mkdir(exist_ok=True)
    CONTENTS_FOLDER.mkdir(exist_ok=True)
    RESPONSES_1_FOLDER.mkdir(exist_ok=True)
    RESPONSES_2_FOLDER.mkdir(exist_ok=True)
    FINAL_FOLDER.mkdir(exist_ok=True)

    # 1. Проходим по всем алертам через RSS, собираем [title, link, content, published] и записываем в json
    # Получается 20 entry на каждый feed

    for feed_name, feed_link in RSS_LINKS.items():
        # feed_path is json
        feed_path = (ALERTS_FOLDER / feed_name).with_suffix(".json")
        feed_alerts = []
        feed = feedparser.parse(feed_link)
        
        # for each entry, gather title, link, content, published
        for entry in feed.entries:
            feed_alerts.append({
                "id": hashlib.sha256(f"{entry.title}{entry.published}".encode()).hexdigest()[:8],
                "title": entry.title,
                "link": entry.link,
                "content": entry.content,
                "published": entry.published
            })
        feed_path.write_text(json.dumps(feed_alerts, indent=4))
        print(f"Feed '{feed_name}' generated {len(feed_alerts)} alerts")
        time.sleep(1)
        
    print("All feeds generated\n----------------------")
    
    # 2. Кидаем в LLM все связи title+content и позволяем ей отобрать релевантные для пользователя
    # Цель: получить FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER+FEEDS_COUNT_CONFUSED релевантных алертов (id)
    # По дороге записываем кол-во токенов (в среднем и всего)

    payload = []
    for feed_path in ALERTS_FOLDER.glob("*.json"):
        alerts = json.loads(feed_path.read_text())
        for alert in alerts:
            payload.append({
                "id": alert["id"],
                "title": alert["title"],
                "content": alert["content"][0]["value"],
            })
    token_count = tiktoken.encoding_for_model("gpt-4o").encode(json.dumps(payload))
    print(f"Tokens (pre-filter): total {len(token_count)}, average {len(token_count) / len(payload)}")

    client = genai.Client(api_key=API_KEY, http_options={"base_url": "https://api.proxyapi.ru/google"})
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=json.dumps(payload),
        config=types.GenerateContentConfig(system_instruction=FILTER_BY_TITLE_AND_CONTENT_PROMPT),
    )
    text_response = str(response.text)
    edited_text_response = text_response.replace("```json", "").replace("```", "")
    json_response = json.loads(edited_text_response)
    (RESPONSES_1_FOLDER / f"{now}.json").write_text(json.dumps(json_response, indent=4))
    
    # 3. По предварительно аппрувнутым от LLM алертам проходим по ссылкам, чистим content (jusText/trafilatura/etc.)
    # Почищенные html записываем в json (папка contents)
    # Далее идем с этими contents к LLM и позволяем ей отобрать FEEDS_COUNT_AFTER_TEXT_FILTER релевантных алертов (id)
    # Ответом будет список id с краткой выжимкой новости (алерта)
    # По дороге записываем кол-во токенов (в среднем и всего)    

    # open 'now' if exist else latest
    with open(get_now_or_latest_file_in_folder(now, RESPONSES_1_FOLDER), "r") as f:
        json_response = json.load(f)
    # пока просто суммируем их (я хз, зачем я решил добавить unsure_ids)
    filtered_ids = json_response["relevant_ids"] + json_response["unsure_ids"]

    contents = {}
    for alert_id in filtered_ids:
        alert = get_alert_by_id(alert_id)
        driver = webdriver.Safari()
        content = get_and_clean_html(driver, alert["link"])[:1000]
        driver.quit()
        contents[alert_id] = content
    (CONTENTS_FOLDER / f"{now}.json").write_text(json.dumps(contents, indent=4))
    
    with open(get_now_or_latest_file_in_folder(now, CONTENTS_FOLDER), "r") as f:
        json_contents = json.load(f)
    
    # count sent tokens
    token_count = tiktoken.encoding_for_model("gpt-4o").encode(json.dumps(json_contents))
    print(f"Tokens (main filter): total {len(token_count)}, average {len(token_count) / len(json_contents)}")
    
    summaries = {}
    for alert_id, alert_text in tqdm.tqdm(json_contents.items(), desc="Filtering by text"):  
        client = genai.Client(api_key=API_KEY, http_options={"base_url": "https://api.proxyapi.ru/google"})
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=alert_text,
            config=types.GenerateContentConfig(system_instruction=FILTER_BY_TEXT_PROMPT),
        )
        text_response = str(response.text)
        try:
            edited_text_response = text_response.replace("```json", "").replace("```", "")
            json_response = json.loads(edited_text_response)
            if not json_response:
                continue
            title, summary = json_response["title"], json_response["summary"]
            summaries[alert_id] = {
                "title": title,
                "summary": summary
            }
        except Exception:
            print(f"Error parsing json (alert {alert_id}). Text: {text_response}")
            continue
        (RESPONSES_2_FOLDER / f"{now}.json").write_text(json.dumps(summaries, indent=4, ensure_ascii=False))
    
    # 5. К id+summary от LLM добавляем link, title и published (обогащаем json)

    with open(get_now_or_latest_file_in_folder(now, RESPONSES_2_FOLDER), "r") as f:
        json_responses = json.load(f)
    new_json = []
    for alert_id, text in json_responses.items():
        title, summary = text["title"], text["summary"]
        alert = get_alert_by_id(alert_id)
        new_json.append({
            "id": alert_id,
            "link": alert["link"],
            "title": title,
            "published": alert["published"],
            "summary": summary
        })
    (FINAL_FOLDER / f"{now}.json").write_text(json.dumps(new_json, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()