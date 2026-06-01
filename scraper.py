def scrape_data():
    all_records = []
    
    # 假设我们爬取前 5 页
    for page in range(1, 6):
        print(f"正在抓取第 {page} 页...")
        url = get_page_url(page)
        
        try:
            # 第一处修改：把 timeout 改为 30 秒
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
                        
                    detail_url = BASE_URL + a['href'].replace('./', '')
                    print(f"  -> 发现数据: {title} ({dt_str})")
                    
                    # 第二处修改：给详情页单独加 try...except，避免一篇文章出错导致整个爬虫崩溃
                    try:
                        # 详情页的 timeout 也改为 30 秒
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
                        # 出错时只打印这篇的错误，然后 continue 继续抓下一篇
                        print(f"  -> 抓取这篇详情页出错，跳过: {inner_e}")
                        continue 
            
        except Exception as e:
            # 这是处理目录页（如第2页、第3页本身）打不开的情况
            print(f"打开第 {page} 页目录时出错: {e}")
            continue # 把 break 改成 continue，目录页出错也只跳过当前目录页

    # 整合所有数据并导出为 CSV
    if all_records:
        final_df = pd.concat(all_records, ignore_index=True)
        cols = final_df.columns.tolist()
        cols = ['观测时间'] + [c for c in cols if c != '观测时间']
        final_df = final_df[cols]
        
        file_path = "yangtze_water_levels.csv"
        final_df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"\n成功保存数据到 {file_path}，共 {len(final_df)} 条记录！")
    else:
        print("未抓取到任何数据。")
