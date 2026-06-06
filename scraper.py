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
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:(\d{1,2})时)?长江水位", title)
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
        if "长江水位" not in title or "长江潮位" in title:
            continue

        observed_time = parse_observed_time(title)
        if not observed_time:
            print(f"跳过无法识别时间的标题: {title}")
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
        return pd.DataFrame(columns=["观测时间", "站点", "水位", "涨落"])

    table = tables[0].copy()
    table.columns = [normalize_text(col) for col in table.columns]

    if not any("站点" in col for col in table.columns) and len(table) > 0:
        table.columns = [normalize_text(col) for col in table.iloc[0].tolist()]
        table = table.iloc[1:].reset_index(drop=True)

    rename_map = {}
    for col in table.columns:
        if "站点" in col:
            rename_map[col] = "站点"
        elif "水位" in col:
            rename_map[col] = "水位"
        elif "涨落" in col:
            rename_map[col] = "涨落"

    table = table.rename(columns=rename_map)
