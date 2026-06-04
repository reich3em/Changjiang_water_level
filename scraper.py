import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ==================== 1. 全局配置 ====================
BASE_URL = "http://www.cjw.gov.cn/zwzc/bmfw/swsq/"  
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# ==================== 2. 辅助工具函数 ====================

def get_page_url(page):
    if page == 1:
        return BASE_URL
    else:
        return f"{BASE_URL}index_{page}.html"

def parse_datetime_from_title(title):
    match = re.search(r'(\d{4}[-\u4e00-\u9fa5]\d{1,2}[-\u4e00-\u9fa5]\d{1,2})', title)
    if match:
        return match.group(1)
    return None

# ==================== 3. 核心爬取主函数 ====================

def scrape_data():
    all_records = []
    
    # 为了排查问题，我们先尝试抓取前 3 页即可（避免盲目请求过多）
    total_pages = 3  
    
    print(f"=== 开始执行抓取流程，目标总页数: {total_pages} ===")
    
    for page in range(1, total_pages + 1):
        url = get_page_url(page)
        print(f"\n[Page {page}] 正在请求目录页: {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.encoding = 'utf-8'
            
            # 🔴 关键排错日志：打印服务器返回的状态码和内容长度
            print(f"[Page {page}] 服务器响应状态码: {response.status_code}, 内容长度: {len(response.text)} 字节")
            
            if response.status_code != 200:
                print(f"[Page {page}] ❌ 请求失败！状态码异常，可能被网站防火墙拦截。")
                continue
                
            # 如果怀疑被拦截，打印前 300 个字符看看到底返回了什么（比如是不是报错页面）
            if "⚡" in response.text or "安全" in response.text or "Forbidden" in response.text or len(response.text) < 1000:
                print(f"[Page {page}] ⚠️ 警告：返回的内容似乎包含拦截提示或页面过短。开头内容预览:\n{response.text[:300]}")

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            print(f"[Page {page}] 当前页面解析到总链接数: {len(links)}")
            
            target_links_count = 0
            for a in links:
                title = a.text.strip()
                # 如果你想看看网页里都有什么标题，可以取消下面这行的注释：
                # print(f"  发现链接文本: {title}")
                
                if '长江水位' in title:
                    target_links_count += 1
                    dt_str = parse_datetime_from_title(title)
                    if not dt_str:
                        continue
                        
                    href = a['href'].replace('./', '')
                    detail_url = href if href.startswith('http') else BASE_URL + href
                    print(f"  -> 🎉 找到目标数据: {title} ({dt_str}) -> 详情页: {detail_url}")
                    
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
                            print(f"     ✅ 成功解析表格数据，包含 {len(df)} 条记录")
                            
                        time.sleep(3) 
                        
                    except Exception as inner_e:
                        print(f"     ❌ 抓取详情页出错: {inner_e}")
                        continue 
            
            print(f"[Page {page}] 页面处理完毕，其中包含'长江水位'的链接数: {target_links_count}")
            
        except Exception as e:
            print(f"[Page {page}] ❌ 打开目录页时发生严重错误: {e}")
            continue

    # ==================== 4. 历史数据合并与保存 ====================
    print("\n=== 开始进行数据保存阶段 ===")
    if all_records:
        new_df = pd.concat(all_records, ignore_index=True)
        cols = new_df.columns.tolist()
        if '观测时间' in cols:
            cols = ['观测时间'] + [c for c in cols if c != '观测时间']
            new_df = new_df[cols]
            
        file_path = "yangtze_water_levels.csv"
        
        if os.path.exists(file_path):
            try:
                print("发现历史 CSV 文件，正在读取并进行增量合并...")
                old_df = pd.read_csv(file_path)
                final_df = pd.concat([old_df, new_df], ignore_index=True)
                
                if '测站' in final_df.columns:
                    final_df.drop_duplicates(subset=['观测时间', '测站'], keep='first', inplace=True)
                elif '站名' in final_df.columns:
                    final_df.drop_duplicates(subset=['观测时间', '站名'], keep='first', inplace=True)
                else:
                    final_df.drop_duplicates(inplace=True)
            except Exception as e:
                print(f"读取历史数据失败({e})，将直接覆盖。")
                final_df = new_df
        else:
            print("未发现历史数据文件，将创建新文件...")
            final_df = new_df
            
        final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"🚀 成功保存！当前文件总记录数: {len(final_df)}")
    else:
        print("❌ 最终结论：本次运行未抓取到任何有效数据，CSV 文件未更新。")

if __name__ == "__main__":
    scrape_data()
