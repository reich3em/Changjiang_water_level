import requests
import re
from bs4 import BeautifulSoup
import pandas as pd
import time
import os

BASE_URL = "https://www.mot.gov.cn/fuwu/yujingtishi/cjshuiweichaowei/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def get_page_url(page_num):
    """根据页码生成对应的URL"""
    if page_num == 1:
        return BASE_URL + "index.html"
    else:
        return BASE_URL + f"index_{page_num - 1}.html"

def parse_datetime_from_title(title):
    """从标题中提取时间，如 '2023年8月1日8时长江水位' -> '2023-08-01 08:00:00'"""
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})时', title)
    if match:
        year, month, day, hour = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:00:00"
    return None

def scrape_data():
    all_records = []
    
    # 假设我们爬取前 5 页 (可根据实际总页数调整 range)
    for page in range(1, 6):
        print(f"正在抓取第 {page} 页...")
        url = get_page_url(page)
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 找到所有详情页链接
            links = soup.find_all('a', href=True)
            for a in links:
                title = a.text.strip()
                if '长江水位' in title:
                    dt_str = parse_datetime_from_title(title)
                    if not dt_str:
                        continue
                        
                    # 拼接详情页绝对路径
                    detail_url = BASE_URL + a['href'].replace('./', '')
                    print(f"  -> 发现数据: {title} ({dt_str})")
                    
                    # 抓取详情页内的表格
                    detail_res = requests.get(detail_url, headers=HEADERS, timeout=10)
                    detail_res.encoding = 'utf-8'
                    
                    # 使用 pandas 提取 HTML 中的表格 (返回 DataFrame 列表)
                    tables = pd.read_html(detail_res.text)
                    if tables:
                        df = tables[0] # 取页面中的第一个表格
                        
                        # 【数据清洗：构建一维表】
                        # 假设原始表格第一行是表头(站点名, 水位等)，这里你可能需要根据实际 HTML 结构微调列名
                        df.columns = df.iloc[0] # 将第一行设为列名
                        df = df[1:].copy()      # 删除第一行数据
                        
                        # 新增标准化时间列
                        df['观测时间'] = dt_str
                        
                        all_records.append(df)
                        
            time.sleep(2) # 礼貌爬取，防止被封 IP
            
        except Exception as e:
            print(f"抓取第 {page} 页时出错: {e}")
            break

    # 整合所有数据并导出为 CSV
    if all_records:
        final_df = pd.concat(all_records, ignore_index=True)
        
        # 调整列顺序，让时间排在第一列 (科学一维表结构)
        cols = final_df.columns.tolist()
        cols = ['观测时间'] + [c for c in cols if c != '观测时间']
        final_df = final_df[cols]
        
        # 如果文件已存在，则追加；不存在则创建
        file_path = "yangtze_water_levels.csv"
        final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"\n成功保存数据到 {file_path}，共 {len(final_df)} 条记录！")
    else:
        print("未抓取到任何数据。")

if __name__ == "__main__":
    scrape_data()
