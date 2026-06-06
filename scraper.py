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
    required_columns = ["站点", "水位", "涨落"]
    missing = [col for col in required_columns if col not in table.columns]
    if missing:
        raise ValueError(f"详情表格缺少字段: {missing}")

    table = table[required_columns].copy()
    table.insert(0, "观测时间", observed_time)

    for col in table.columns:
        table[col] = table[col].map(normalize_text)

    table = table[table["站点"].ne("")]
    return table


def merge_and_save(new_df):
    new_df = new_df[["观测时间", "站点", "水位", "涨落"]].copy()

    if os.path.exists(CSV_PATH):
        old_df = pd.read_csv(CSV_PATH, dtype=str)
        final_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        final_df = new_df

    final_df = final_df[["观测时间", "站点", "水位", "涨落"]]
    final_df = final_df.drop_duplicates(subset=["观测时间", "站点"], keep="last")
    final_df = final_df.sort_values(["观测时间", "站点"]).reset_index(drop=True)
    final_df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    return final_df


def scrape_data():
    session = requests.Session()
    print(f"开始请求入口页: {INDEX_URL}")
    index_html = fetch_html(session, INDEX_URL)
    links = find_water_level_links(index_html)
    print(f"入口页发现长江水位详情链接: {len(links)} 个")

    all_frames = []
    for item in links:
        print(f"抓取详情: {item['title']} -> {item['url']}")
        try:
            detail_html = fetch_html(session, item["url"])
            df = parse_detail_table(detail_html, item["observed_time"])
            if df.empty:
                print("  未解析到表格数据")
                continue

            all_frames.append(df)
            print(f"  成功解析 {len(df)} 条记录")
            time.sleep(1)
        except Exception as exc:
            print(f"  详情页处理失败: {exc}")

    if not all_frames:
        print("本次未抓取到任何有效数据，CSV 文件未更新。")
        return

    new_df = pd.concat(all_frames, ignore_index=True)
    final_df = merge_and_save(new_df)
    print(f"保存完成: 本次抓取 {len(new_df)} 条，CSV 当前总计 {len(final_df)} 条。")


if __name__ == "__main__":
    scrape_data()
