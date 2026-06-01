import os
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

def scrape_data():
    all_records = []
    
    # 1. 修改这里：填入您在网站上看到的实际总页数（比如一共 50 页，就写 50）
    # 💡 建议：第一次为了拿全量历史数据，可以写大一点（如 50）；
    #    等全量数据拿到后，日常每天自动化运行只需改成 2 或 3 页即可（省时且防止被封IP）
    total_pages = 24  
    
    for page in range(1, total_pages + 1):
        print(f"正在抓取第 {page} 页...")
        url = get_page_url(page)
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = soup.find_all('a', href=True)
            for a in links:
                title = a.text.strip()
                if '长江水位' in title:
                    dt_str = parse_datetime_from_title(title)
                    if not dt_str:
                        continue
                        
                    detail_url = BASE_URL + a['href'].replace('./', '')
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
                            
                        time.sleep(3) 
                        
                    except Exception as inner_e:
                        print(f"  -> 抓取这篇详情页出错，跳过: {inner_e}")
                        continue 
            
        except Exception as e:
            print(f"打开第 {page} 页目录时出错: {e}")
            continue

    # 2. 整合并增量累积保存数据
    if all_records:
        new_df = pd.concat(all_records, ignore_index=True)
        cols = new_df.columns.tolist()
        cols = ['观测时间'] + [c for c in cols if c != '观测时间']
        new_df = new_df[cols]
        
        file_path = "yangtze_water_levels.csv"
        
        # 核心修改：如果已有历史文件，先读取并合并去重，防止覆盖
        if os.path.exists(file_path):
            try:
                old_df = pd.read_csv(file_path)
                final_df = pd.concat([old_df, new_df], ignore_index=True)
                
                # 根据“观测时间”和您表格里的“测站”列进行去重
                # ⚠️ 请把下面的 '测站' 替换为您 CSV 里的实际站点列名（如 '站名'、'测站名称'）
                if '测站' in final_df.columns:
                    final_df.drop_duplicates(subset=['观测时间', '测站'], keep='first', inplace=True)
                else:
                    final_df.drop_duplicates(inplace=True)
                print(f"成功与历史数据合并，去重后当前总记录数: {len(final_df)}")
            except Exception as e:
                print(f"读取历史数据失败({e})，将直接覆盖保存新数据。")
                final_df = new_df
        else:
            final_df = new_df
            
        # 写入文件
        final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"\n成功保存数据到 {file_path}，当前文件内总共 {len(final_df)} 条记录！")
    else:
        print("未抓取到任何数据。")
