#!/usr/bin/env python3
"""
eBay Seller Hub並列処理版サンプル
- 複数のブラウザウィンドウを使用して並列処理
- 大量データの高速処理用
"""

import pandas as pd
import time
from datetime import datetime
import os
import concurrent.futures
from multiprocessing import cpu_count
import threading

# 既存のインポートと関数を使用
from extract_ebay_seller_hub_config import (
    load_config, setup_driver, extract_model_numbers, 
    parse_price, calculate_minimum_ebay_price,
    search_model_number, apply_price_filter_if_enabled,
    extract_highest_price_product
)

# グローバルロック（ファイル書き込み用）
write_lock = threading.Lock()

def process_single_item(item_data, config, worker_id):
    """
    単一アイテムを処理する関数（並列実行用）
    """
    index, row, product_name, mercari_price_text = item_data
    
    try:
        print(f"[Worker {worker_id}] 🔄 処理中: 商品 #{index+1}")
        
        mercari_price = parse_price(mercari_price_text)
        model_numbers = extract_model_numbers(product_name)
        
        if not model_numbers:
            print(f"[Worker {worker_id}] ⚠️ 型番が見つかりません: {product_name}")
            return None
        
        model_number = model_numbers[0]
        print(f"[Worker {worker_id}] 🎯 型番: {model_number}")
        
        # 各ワーカーが独自のドライバーを使用
        driver = setup_driver()
        if not driver:
            return None
        
        try:
            # eBay Seller Hubにアクセス
            driver.get("https://www.ebay.com/sh/research?marketplace=EBAY-US&tabName=SOLD")
            
            # 最初のワーカーのみログイン待機
            if worker_id == 1:
                print(f"[Worker {worker_id}] 🔐 手動ログインを実行してください")
                input("ログイン完了後、Enterキーを押してください...")
                time.sleep(2)
            else:
                # 他のワーカーは少し待機してから開始
                time.sleep(5 * worker_id)
            
            # 型番を検索
            if search_model_number(driver, model_number):
                apply_price_filter_if_enabled(driver, config)
                highest_product = extract_highest_price_product(driver, model_number, mercari_price, config)
                
                if highest_product:
                    profit_amount = highest_product['price_numeric'] - mercari_price
                    
                    result = {
                        'index': index,
                        'eBay商品名': highest_product['item_name'],
                        'eBayURL': highest_product['item_url'],
                        'eBay価格(USD)': highest_product['price'],
                        'eBay価格(JPY)': f"¥{highest_product['price_numeric']:,.0f}",
                        '利益金額': f"¥{profit_amount:,.0f}",
                        '利益判定': 'OK'
                    }
                    
                    print(f"[Worker {worker_id}] ✅ 成功: {model_number}")
                    return result
                    
            print(f"[Worker {worker_id}] ⚠️ 商品が見つかりません: {model_number}")
            return None
            
        finally:
            driver.quit()
            
    except Exception as e:
        print(f"[Worker {worker_id}] ❌ エラー: {e}")
        return None

def process_csv_parallel(csv_file_path, max_workers=3):
    """
    CSVファイルを並列処理
    """
    try:
        # 設定を読み込み
        config = load_config()
        
        # CSVファイルを読み込み
        df = pd.read_csv(csv_file_path, encoding='utf-8')
        print(f"📁 CSVファイル読み込み: {len(df)}行")
        
        # 結果用のDataFrameを準備
        result_df = df.copy()
        result_df['eBay商品名'] = ''
        result_df['eBayURL'] = ''
        result_df['eBay価格(USD)'] = ''
        result_df['eBay価格(JPY)'] = ''
        result_df['利益金額'] = ''
        result_df['利益判定'] = ''
        
        # 処理するアイテムのリストを作成
        items_to_process = []
        for index, row in df.iterrows():
            if 'title' in df.columns:
                product_name = str(row['title'])
            else:
                product_name = str(row.iloc[0])
                
            if 'price' in df.columns:
                mercari_price_text = str(row['price'])
            else:
                mercari_price_text = str(row.iloc[2])
                
            items_to_process.append((index, row, product_name, mercari_price_text))
        
        # 並列処理の実行
        print(f"\n🚀 並列処理開始（ワーカー数: {max_workers}）")
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 各アイテムをワーカーに割り当て
            future_to_item = {}
            for i, item in enumerate(items_to_process):
                worker_id = (i % max_workers) + 1
                future = executor.submit(process_single_item, item, config, worker_id)
                future_to_item[future] = item[0]  # index
            
            # 結果を収集
            completed = 0
            for future in concurrent.futures.as_completed(future_to_item):
                completed += 1
                print(f"⏳ 進捗: {completed}/{len(items_to_process)} ({completed/len(items_to_process)*100:.1f}%)")
                
                result = future.result()
                if result:
                    index = result['index']
                    for key, value in result.items():
                        if key != 'index':
                            result_df.at[index, key] = value
        
        # 処理時間を計算
        elapsed_time = time.time() - start_time
        print(f"\n⏱️ 処理時間: {elapsed_time:.1f}秒 ({elapsed_time/60:.1f}分)")
        print(f"📊 平均処理時間: {elapsed_time/len(df):.1f}秒/件")
        
        # 結果を保存
        # 入力ファイル名から拡張子を除いた名前を取得
        input_base_name = os.path.splitext(os.path.basename(csv_file_path))[0]
        output_filename = f"{input_base_name}_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        result_df.to_csv(output_filename, index=False, encoding='utf-8')
        print(f"\n💾 結果保存: {output_filename}")
        
        return result_df
        
    except Exception as e:
        print(f"❌ 並列処理エラー: {e}")
        return None

def main():
    """
    メイン処理
    """
    print("=" * 60)
    print("🚀 eBay Seller Hub並列処理版")
    print("⚡ 複数のブラウザで高速処理")
    print("=" * 60)
    
    # CSVファイルパスを入力
    csv_file_path = input("📁 CSVファイルのパスを入力してください: ").strip()
    
    if not os.path.exists(csv_file_path):
        print(f"❌ ファイルが見つかりません: {csv_file_path}")
        return
    
    # ワーカー数を選択
    max_workers = int(input("🔢 同時実行するブラウザ数を入力 (推奨: 2-4): ") or "3")
    
    # 処理実行
    result = process_csv_parallel(csv_file_path, max_workers)
    
    if result is not None:
        print("\n✅ 処理完了！")
        print(f"📊 処理結果: {len(result)}行")
    else:
        print("\n❌ 処理に失敗しました")

if __name__ == "__main__":
    main() 