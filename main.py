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
from checkpoint import CheckpointManager, STAGES

# safari selenium
from selenium import webdriver

# Initialize checkpoint manager
checkpoint_mgr = CheckpointManager()


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
    checkpoint_mgr.update_stats(
        current_stage=STAGES["INIT"],
        stage_progress=0.0
    )
    
    now = int(datetime.datetime.now().timestamp())
    ALERTS_FOLDER.mkdir(exist_ok=True)
    CONTENTS_FOLDER.mkdir(exist_ok=True)
    RESPONSES_1_FOLDER.mkdir(exist_ok=True)
    RESPONSES_2_FOLDER.mkdir(exist_ok=True)
    FINAL_FOLDER.mkdir(exist_ok=True)

    # 1. Проходим по всем алертам через RSS, собираем [title, link, content, published] и записываем в json
    # Получается 20 entry на каждый feed

    checkpoint_mgr.update_stats(
        current_stage=STAGES["RSS_FETCH"],
        stage_progress=0.0,
        total_alerts=0
    )
    
    total_feeds = len(RSS_LINKS)
    for idx, (feed_name, feed_link) in enumerate(RSS_LINKS.items(), 1):
        checkpoint_mgr.update_stats(
            current_feed=feed_name,
            stage_progress=idx/total_feeds,
            stage_details=f"Processing feed {idx}/{total_feeds}"
        )
        
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
        
        checkpoint_mgr.update_stats(
            total_alerts=checkpoint_mgr.stats.total_alerts + len(feed_alerts)
        )
        print(f"Feed '{feed_name}' generated {len(feed_alerts)} alerts")
        time.sleep(1)
        
    print("All feeds generated\n----------------------")
    
    # 2. Кидаем в LLM все связи title+content и позволяем ей отобрать релевантные для пользователя
    # Цель: получить FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER+FEEDS_COUNT_CONFUSED релевантных алертов (id)
    # По дороге записываем кол-во токенов (в среднем и всего)

    checkpoint_mgr.update_stats(
        current_stage=STAGES["FIRST_FILTER"],
        stage_progress=0.0,
        stage_details="Preparing content for first filter"
    )
    
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
    total_tokens = len(token_count)
    avg_tokens = total_tokens / len(payload)
    
    checkpoint_mgr.update_stats(
        tokens_processed=total_tokens,
        avg_tokens_per_item=avg_tokens,
        stage_progress=0.3,
        stage_details="Content prepared, starting AI filtering"
    )
    
    print(f"Tokens (pre-filter): total {total_tokens}, average {avg_tokens}")

    client = genai.Client(api_key=API_KEY, http_options={"base_url": "https://api.proxyapi.ru/google"})
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=json.dumps(payload),
        config=types.GenerateContentConfig(system_instruction=FILTER_BY_TITLE_AND_CONTENT_PROMPT),
    )
    text_response = str(response.text)
    edited_text_response = text_response.replace("```json", "").replace("```", "")
    json_response = json.loads(edited_text_response)
    
    checkpoint_mgr.update_stats(
        stage_progress=1.0,
        filtered_count=len(json_response.get("relevant_ids", [])) + len(json_response.get("unsure_ids", [])),
        stage_details="First filter complete"
    )
    
    (RESPONSES_1_FOLDER / f"{now}.json").write_text(json.dumps(json_response, indent=4))
    
    # 3. По предварительно аппрувнутым от LLM алертам проходим по ссылкам, чистим content (jusText/trafilatura/etc.)
    # Почищенные html записываем в json (папка contents)
    # Далее идем с этими contents к LLM и позволяем ей отобрать FEEDS_COUNT_AFTER_TEXT_FILTER релевантных алертов (id)
    # Ответом будет список id с краткой выжимкой новости (алерта)
    # По дороге записываем кол-во токенов (в среднем и всего)    

    checkpoint_mgr.update_stats(
        current_stage=STAGES["CONTENT_FETCH"],
        stage_progress=0.0,
        stage_details="Starting content fetch"
    )
    
    # open 'now' if exist else latest
    with open(get_now_or_latest_file_in_folder(now, RESPONSES_1_FOLDER), "r") as f:
        json_response = json.load(f)
    # пока просто суммируем их (я хз, зачем я решил добавить unsure_ids)
    filtered_ids = json_response["relevant_ids"] + json_response["unsure_ids"]

    contents = {}
    error_count = 0
    for idx, alert_id in enumerate(filtered_ids, 1):
        try:
            alert = get_alert_by_id(alert_id)
            checkpoint_mgr.update_stats(
                stage_progress=idx/len(filtered_ids),
                stage_details=f"Fetching content {idx}/{len(filtered_ids)}: {alert['title'][:50]}..."
            )
            
            driver = webdriver.Safari()
            content = get_and_clean_html(driver, alert["link"])[:1000]
            driver.quit()
            contents[alert_id] = content
        except Exception as e:
            print(f"Error fetching content for alert {alert_id}: {e}")
            error_count += 1
            checkpoint_mgr.update_stats(error_count=error_count)
            continue
            
    checkpoint_mgr.update_stats(
        stage_progress=1.0,
        stage_details="Content fetch complete"
    )
    (CONTENTS_FOLDER / f"{now}.json").write_text(json.dumps(contents, indent=4))
    
    checkpoint_mgr.update_stats(
        current_stage=STAGES["SECOND_FILTER"],
        stage_progress=0.0,
        stage_details="Starting second filter"
    )
    
    with open(get_now_or_latest_file_in_folder(now, CONTENTS_FOLDER), "r") as f:
        json_contents = json.load(f)
    
    # count sent tokens
    token_count = tiktoken.encoding_for_model("gpt-4o").encode(json.dumps(json_contents))
    total_tokens = len(token_count)
    avg_tokens = total_tokens / len(json_contents)
    
    checkpoint_mgr.update_stats(
        tokens_processed=checkpoint_mgr.stats.tokens_processed + total_tokens,
        avg_tokens_per_item=(checkpoint_mgr.stats.avg_tokens_per_item + avg_tokens) / 2,
        stage_progress=0.2,
        stage_details="Content prepared for second filter"
    )
    
    print(f"Tokens (main filter): total {total_tokens}, average {avg_tokens}")
    
    summaries = {}
    error_count = checkpoint_mgr.stats.error_count
    for idx, (alert_id, alert_text) in enumerate(json_contents.items(), 1):
        checkpoint_mgr.update_stats(
            stage_progress=0.2 + 0.8 * (idx/len(json_contents)),
            stage_details=f"Processing alert {idx}/{len(json_contents)}"
        )
        
        try:
            client = genai.Client(api_key=API_KEY, http_options={"base_url": "https://api.proxyapi.ru/google"})
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=alert_text,
                config=types.GenerateContentConfig(system_instruction=FILTER_BY_TEXT_PROMPT),
            )
            text_response = str(response.text)
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
            error_count += 1
            checkpoint_mgr.update_stats(error_count=error_count)
            continue
            
        checkpoint_mgr.update_stats(
            filtered_count=len(summaries)
        )
        (RESPONSES_2_FOLDER / f"{now}.json").write_text(json.dumps(summaries, indent=4, ensure_ascii=False))
    
    # 5. К id+summary от LLM добавляем link, title и published (обогащаем json)

    checkpoint_mgr.update_stats(
        current_stage=STAGES["FINAL"],
        stage_progress=0.0,
        stage_details="Starting final processing"
    )
    
    with open(get_now_or_latest_file_in_folder(now, RESPONSES_2_FOLDER), "r") as f:
        json_responses = json.load(f)
    new_json = []
    
    for idx, (alert_id, text) in enumerate(json_responses.items(), 1):
        checkpoint_mgr.update_stats(
            stage_progress=idx/len(json_responses),
            stage_details=f"Finalizing alert {idx}/{len(json_responses)}"
        )
        
        title, summary = text["title"], text["summary"]
        alert = get_alert_by_id(alert_id)
        new_json.append({
            "id": alert_id,
            "link": alert["link"],
            "title": title,
            "published": alert["published"],
            "summary": summary
        })
    
    checkpoint_mgr.update_stats(
        stage_progress=1.0,
        stage_details="Processing complete",
        filtered_count=len(new_json)
    )
    
    (FINAL_FOLDER / f"{now}.json").write_text(json.dumps(new_json, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()