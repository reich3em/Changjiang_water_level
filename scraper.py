import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ==================== 1. 全局配置 ====================
# ⚠️ 请确保这里的 BASE_URL 和 HEADERS 与你原本脚本里写的一致
BASE_URL = "http://www.cjw.gov.cn/zwzc/bmfw/swsq/"  
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ==================== 2. 辅助工具函数 ====================

def get_page_url(page):
    """
    根据页码生成目录页的完整 URL
    ⚠️ 如果你之前写过更精准的翻页 URL 拼接逻辑，请用你原先的代码替换这部分
    """
    if page == 1:
        return BASE_URL
    else:
        return f"{BASE_URL}index_{page}.html"

def parse_datetime_from_title(title):
    """
    从标题中提取日期时间（例如：从"长江水位2026-06-01"中提取"2026-06-01"）
    ⚠️ 如果你之前有特定的正则解析规则，请用你原先的代码替换这部分
    """
    match = re.search(r'(\d{4}[-\u4e00-\u9fa5]\d{1,2}[-\u4e00-\u9fa5]\d{1,2})', title)
    if match:
        return match.group(1)
    return None

# ==================== 3. 核心爬取主函数 ====================

def scrape_data():
    all_records = []
    
    # 💡 核心修改一：在这里填入你看到的网站实际总页数（例如一共 50 页）
    # 第一次为了把几个月、几年的历史数据拿全，可以设大一点（如 50）；
    # 拿完历史全量数据后，日常维护建议改回 2 或 3，只抓最新页，节省 Actions 时间。
    total_pages = 23  
    
    for page in range(1, total_pages + 1):
        print(f"正在抓取第 {page} 页...")
        url = get_page_url(page)
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
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
                        
                    # 处理网址相对路径
                    href = a['href'].replace('./', '')
                    detail_url = href if href.startswith('http') else BASE_URL + href
                    print(f"  -> 发现数据: {title} ({dt_str})")
                    
                    try:
                        detail_res = requests.get(detail_url, headers=HEADERS, timeout=30)
                        detail_res.encoding = 'utf-8'
                        
                        tables = pd.read_html(detail_res.text)
                        if tables:
                            df = tables[0] 
                            df.columns = df.iloc[0] 
                            df = df[1:].copy()      
                            df['观测时间'] = dt_str
                            all_records.append(df)
                            
                        # 每抓完一篇，休息 3 秒，防止被官方网站封锁 IP
                        time.sleep(3) 
                        
                    except Exception as inner_e:
                        print(f"  -> 抓取这篇详情页出错，跳过: {inner_e}")
                        continue 
            
        except Exception as e:
            print(f"打开第 {page} 页目录时出错: {e}")
            continue

    # ==================== 4. 历史数据【增量累积】与保存 ====================
    if all_records:
        new_df = pd.concat(all_records, ignore_index=True)
        cols = new_df.columns.tolist()
        if '观测时间' in cols:
            cols = ['观测时间'] + [c for c in cols if c != '观测时间']
            new_df = new_df[cols]
            
        file_path = "yangtze_water_levels.csv"
        
        # 核心修改二：检查仓库里是否已经存在历史 CSV 文件
        if os.path.exists(file_path):
            try:
                print("发现历史 CSV 文件，正在读取并进行增量合并...")
                old_df = pd.read_csv(file_path)
                
                # 将老历史数据和今天新抓的数据拼在一起
                final_df = pd.concat([old_df, new_df], ignore_index=True)
                
                # 核心去重：防止重复写入相同的测站在同一时间的数据
                # ⚠️ 请确认你的 CSV 里的站点列名叫什么，代码会自动适配 '测站' 或 '站名'
                if '测站' in final_df.columns:
                    final_df.drop_duplicates(subset=['观测时间', '测站'], keep='first', inplace=True)
                elif '站名' in final_df.columns:
                    final_df.drop_duplicates(subset=['观测时间', '站名'], keep='first', inplace=True)
                else:
                    final_df.drop_duplicates(inplace=True)
                    
                print(f"数据合并去重成功！当前总记录数: {len(final_df)}")
            except Exception as e:
                print(f"读取历史数据失败({e})，将直接用新抓取的数据覆盖保存。")
                final_df = new_df
        else:
            print("未发现历史数据文件，将创建新文件...")
            final_df = new_df
            
        # 重新存回仓库中的原文件
        final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"\n成功保存数据到 {file_path}，当前文件内总共包含 {len(final_df)} 条历史记录！")
    else:
        print("未抓取到任何数据。")

# ==================== 5. 程序唯一执行入口 ====================
# 核心修复三：确保 GitHub Actions 在调用 python scraper.py 时能真正开始执行
if __name__ == "__main__":
    scrape_data()
