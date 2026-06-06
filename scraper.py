import os
import re
import time
from io import StringIO
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


INDEX_URL = "https://www.mot.gov.cn/fuwu/yujingtishi/cjshuiweichaowei/index.html"
CSV_PATH = "yangtze_water_levels.csv"

TEXT_WATER_LEVEL = "\u957f\u6c5f\u6c34\u4f4d"
TEXT_TIDE_LEVEL = "\u957f\u6c5f\u6f6e\u4f4d"
COL_OBSERVED_TIME = "\u89c2\u6d4b\u65f6\u95f4"
COL_STATION = "\u7ad9\u70b9"
COL_LEVEL = "\u6c34\u4f4d"
COL_CHANGE = "\u6da8\u843d"

OUTPUT_COLUMNS = [COL_OBSERVED_TIME, COL_STATION, COL_LEVEL, COL_CHANGE]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.mot.gov.cn/",
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def fetch_html(session, url):
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def parse_observed_time(title):
    pattern = (
        r"(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5"
        r"(?:(\d{1,2})\u65f6)?\u957f\u6c5f\u6c34\u4f4d"
    )
    match = re.search(pattern, title)
    if not match:
        return None

    year, month, day, hour = match.groups()
    hour = hour or "8"
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d} {int(hour):02d}:00:00"


def find_water_level_links(index_html):
    soup = BeautifulSoup(index_html, "lxml")
    links = []
    seen = set()

    for anchor in soup.select("a[href]"):
        title = normalize_text(anchor.get_text())
        href = anchor.get("href", "")
        if TEXT_WATER_LEVEL not in title or TEXT_TIDE_LEVEL in title:
            continue

        observed_time = parse_observed_time(title)
        if not observed_time:
            print(f"Skip title with unknown time: {title}")
            continue

        detail_url = urljoin(INDEX_URL, href)
        if detail_url in seen:
            continue

        seen.add(detail_url)
        links.append(
            {
                "title": title,
                "url": detail_url,
                "observed_time": observed_time,
            }
        )

    return links


def parse_detail_table(detail_html, observed_time):
    tables = pd.read_html(StringIO(detail_html))
    if not tables:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    table = tables[0].copy()
    table.columns = [normalize_text(col) for col in table.columns]

    if not any(COL_STATION in col for col in table.columns) and len(table) > 0:
        table.columns = [normalize_text(col) for col in table.iloc[0].tolist()]
        table = table.iloc[1:].reset_index(drop=True)

    rename_map = {}
    for col in table.columns:
        if COL_STATION in col:
            rename_map[col] = COL_STATION
        elif COL_LEVEL in col:
            rename_map[col] = COL_LEVEL
        elif COL_CHANGE in col:
            rename_map[col] = COL_CHANGE

    table = table.rename(columns=rename_map)
    required_columns = [COL_STATION, COL_LEVEL, COL_CHANGE]
    missing = [col for col in required_columns if col not in table.columns]
    if missing:
        raise ValueError(f"Missing detail table columns: {missing}")

    table = table[required_columns].copy()
    table.insert(0, COL_OBSERVED_TIME, observed_time)

    for col in table.columns:
        table[col] = table[col].map(normalize_text)

    table = table[table[COL_STATION].ne("")]
    return table


def merge_and_save(new_df):
    new_df = new_df[OUTPUT_COLUMNS].copy()

    if os.path.exists(CSV_PATH):
        old_df = pd.read_csv(CSV_PATH, dtype=str)
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df

    final_df = final_df[OUTPUT_COLUMNS]
    final_df = final_df.drop_duplicates(subset=[COL_OBSERVED_TIME, COL_STATION], keep="last")
    final_df = final_df.sort_values([COL_OBSERVED_TIME, COL_STATION]).reset_index(drop=True)
    final_df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    return final_df


def scrape_data():
    session = requests.Session()
    print(f"Fetching index page: {INDEX_URL}")
    index_html = fetch_html(session, INDEX_URL)
    links = find_water_level_links(index_html)
    print(f"Found water-level detail links: {len(links)}")

    all_frames = []
    for item in links:
        print(f"Fetching detail: {item['title']} -> {item['url']}")
        try:
            detail_html = fetch_html(session, item["url"])
            df = parse_detail_table(detail_html, item["observed_time"])
            if df.empty:
                print("  No table rows parsed")
                continue

            all_frames.append(df)
            print(f"  Parsed rows: {len(df)}")
            time.sleep(1)
        except Exception as exc:
            print(f"  Detail page failed: {exc}")

    if not all_frames:
        print("No valid rows were scraped; CSV was not changed.")
        return

    new_df = pd.concat(all_frames, ignore_index=True)
    final_df = merge_and_save(new_df)
    print(f"Saved CSV. New rows scraped: {len(new_df)}. Total rows: {len(final_df)}.")


if __name__ == "__main__":
    scrape_data()
