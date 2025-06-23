#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay Seller Hub設定対応版 - Config.yamlから利益計算設定を読み込み
"""

import re
import json
import csv
import pandas as pd
from datetime import datetime
import os
import time
import yaml
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys

def load_config():
    """
    config.yamlから設定を読み込み
    """
    try:
        config_path = "config/config.yaml"
        if not os.path.exists(config_path):
            print(f"⚠️ 設定ファイルが見つかりません: {config_path}")
            print("デフォルト設定を使用します")
            return {
                'profit_calculation': {
                    'markup_rate': 0.2,  # 20%
                    'fixed_profit': 3000  # 3000円
                },
                'exchange_rate': {
                    'fixed_rate': 150.0
                }
            }
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        print(f"📋 設定ファイル読み込み: {config_path}")
        markup_rate = config['profit_calculation']['markup_rate']
        fixed_profit = config['profit_calculation']['fixed_profit']
        exchange_rate = config['exchange_rate']['fixed_rate']
        
        print(f"💰 利益率設定: {markup_rate*100:.1f}%")
        print(f"💰 固定利益: ¥{fixed_profit:,}")
        print(f"💱 為替レート: 1USD = ¥{exchange_rate}")
        
        return config
        
    except Exception as e:
        print(f"❌ 設定ファイル読み込みエラー: {e}")
        print("デフォルト設定を使用します")
        return {
            'profit_calculation': {
                'markup_rate': 0.2,
                'fixed_profit': 3000
            },
            'exchange_rate': {
                'fixed_rate': 150.0
            }
        }

def calculate_minimum_ebay_price(mercari_price, config):
    """
    メルカリ価格から必要なeBay最低価格を計算
    """
    markup_rate = config['profit_calculation']['markup_rate']
    fixed_profit = config['profit_calculation']['fixed_profit']
    
    # メルカリ価格 × (1 + 利益率) + 固定利益
    minimum_price = mercari_price * (1 + markup_rate) + fixed_profit
    
    return minimum_price

def setup_driver():
    """
    Seleniumドライバーをセットアップ
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # ヘッドレスモードを無効にして手動ログインを可能にする
    # chrome_options.add_argument("--headless")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ ドライバーセットアップエラー: {e}")
        return None

def extract_model_numbers(text):
    """
    商品名から型番を抽出（改善版）
    """
    if not text:
        return []
    
    # 「のサムネイル」などの余計な文字を除去
    text = re.sub(r'のサムネイル$', '', text)
    text = re.sub(r'サムネイル$', '', text)
    
    patterns = [
        r'\b[A-Z]{2,4}[0-9]{3,4}[A-Z]?\b',  # 腕時計型番 (例: SBGX263, SBGA211)
        r'\b[0-9]{4}-[0-9]{4}\b',           # ハイフン付き型番 (例: 5645-7010)
        r'\b[A-Z]{1,2}[0-9]{3,6}[A-Z]?\b', # 家電型番 (例: KJ55X8500G)
        r'\b[0-9]{3,6}[A-Z]{2,4}\b',       # 数字+文字型番
    ]
    
    found_models = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found_models.extend(matches)
    
    return list(set(found_models))  # 重複を除去

def parse_price(price_text):
    """
    価格文字列から数値を抽出
    """
    if not price_text:
        return 0.0
    
    # 文字列から数字部分のみを抽出
    # $1,625.00 → 1625.0
    # ¥150,000 → 150000.0
    price_match = re.search(r'[\d,]+\.?\d*', str(price_text).replace(',', ''))
    if price_match:
        try:
            return float(price_match.group().replace(',', ''))
        except ValueError:
            return 0.0
    return 0.0

def wait_for_manual_login(driver):
    """
    手動ログインを待機
    """
    print("🔐 手動ログインを実行してください:")
    print("1. eBayアカウントでログイン")
    print("2. Product Research画面が表示されるまで待機")
    print("3. 準備ができたらEnterキーを押してください")
    
    input("ログイン完了後、Enterキーを押してください...")
    
    # ログイン後のページ読み込み待機
    time.sleep(3)

def search_model_number(driver, model_number):
    """
    型番を検索窓に入力して検索実行
    """
    try:
        print(f"🔍 型番 '{model_number}' を検索中...")
        
        # 検索窓のセレクター
        search_selectors = [
            "input.textbox_control",  # メインの検索入力
            "input[placeholder*='Enter keywords']",  # プレースホルダーから特定
            ".search-input-panel input",  # パネル内のinput
            "input[maxlength='500']",  # 最大文字数から特定
        ]
        
        search_input = None
        for selector in search_selectors:
            try:
                search_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"✅ 検索窓発見: {selector}")
                break
            except TimeoutException:
                continue
        
        if not search_input:
            print("❌ 検索窓が見つかりません")
            return False
        
        # 検索窓を完全にクリアして型番を入力
        search_input.clear()
        time.sleep(0.5)  # クリア処理の完了を待機
        
        # Ctrl+A → Delete で確実にクリア
        search_input.send_keys(Keys.CONTROL + "a")
        time.sleep(0.2)
        search_input.send_keys(Keys.DELETE)
        time.sleep(0.2)
        
        # 型番を入力
        search_input.send_keys(model_number)
        time.sleep(1)
        
        # 入力内容を確認（デバッグ用）
        current_value = search_input.get_attribute('value')
        print(f"🔍 検索窓の内容確認: '{current_value}'")
        
        # Enterキーで検索実行
        search_input.send_keys(Keys.RETURN)
        print(f"🔍 検索実行: {model_number}")
        
        # 検索結果の読み込み待機（延長）
        print("⏳ 検索結果の読み込み待機中...")
        time.sleep(8)  # 5秒から8秒に延長
        
        return True
        
    except Exception as e:
        print(f"❌ 検索エラー: {e}")
        return False

def extract_highest_price_product(driver, model_number, mercari_price, config):
    """
    検索結果から設定に基づく利益条件を満たす最高価格のアイテムを抽出
    """
    try:
        print(f"📊 商品データ抽出開始: {model_number}")
        print(f"💰 メルカリ基準価格: ¥{mercari_price:,.0f}")
        
        # 必要なeBay最低価格を計算
        minimum_ebay_price = calculate_minimum_ebay_price(mercari_price, config)
        print(f"📈 必要なeBay最低価格: ¥{minimum_ebay_price:,.0f}")
        
        # デバッグ用HTMLを保存
        html_content = driver.page_source
        debug_filename = f"seller_hub_config_{model_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(debug_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"💾 デバッグHTML保存: {debug_filename}")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # research-table-row全体を取得してデータを組み合わせ
        table_rows = soup.find_all('tr', class_='research-table-row')
        print(f"📋 テーブル行: {len(table_rows)}件")
        
        profitable_products = []
        exchange_rate = config['exchange_rate']['fixed_rate']
        
        for i, row in enumerate(table_rows):
            product = {
                'item_name': '',
                'item_url': '',
                'price': '',
                'price_numeric': 0.0,
                'usd_price': 0.0,
                'is_profitable': False
            }
            
            # 商品名
            name_element = row.find('span', {'data-item-id': True})
            if name_element:
                product['item_name'] = name_element.get_text(strip=True)
            
            # URL
            url_element = row.find('a', class_='research-table-row__link-row-anchor')
            if url_element:
                href = url_element.get('href', '')
                if href and not href.startswith('http'):
                    href = 'https://www.ebay.com' + href
                product['item_url'] = href
            
            # 価格（売れた価格を取得）
            price_element = row.find('td', class_='research-table-row__avgSoldPrice')
            if price_element:
                price_div = price_element.find('div', class_='research-table-row__item-with-subtitle')
                if price_div:
                    price_text = price_div.get_text(strip=True)
                    # 価格から数値部分を抽出
                    price_match = re.search(r'\$[\d,]+\.?\d*', price_text)
                    if price_match:
                        product['price'] = price_match.group()
                        # USD to JPY 変換（設定ファイルのレートを使用）
                        usd_price = parse_price(price_match.group())
                        jpy_price = usd_price * exchange_rate
                        product['usd_price'] = usd_price
                        product['price_numeric'] = jpy_price
                        
                        # 設定に基づく利益判定
                        if jpy_price >= minimum_ebay_price:
                            product['is_profitable'] = True
                            actual_profit = jpy_price - mercari_price
                            print(f"  💰 利益商品発見: {product['item_name'][:30]}... - ${usd_price:.2f} (¥{jpy_price:,.0f}) 利益:¥{actual_profit:,.0f}")
            
            # 利益が出る商品のみ追加
            if product['is_profitable'] and any([product['item_name'], product['item_url'], product['price']]):
                profitable_products.append(product)
        
        # 最高価格の商品を選択
        if profitable_products:
            # USD価格で並び替えて最高価格を取得
            highest_price_product = max(profitable_products, key=lambda x: x['usd_price'])
            
            print(f"✅ 最高価格商品選択: {len(profitable_products)}件中から選択")
            print(f"  🏆 最高価格: ${highest_price_product['usd_price']:.2f} (¥{highest_price_product['price_numeric']:,.0f})")
            print(f"  📝 商品名: {highest_price_product['item_name'][:50]}...")
            print(f"  💰 実際の利益: ¥{highest_price_product['price_numeric'] - mercari_price:,.0f}")
            
            return highest_price_product
        else:
            print(f"⚠️ 設定条件を満たす利益商品が見つかりません")
            return None
        
    except Exception as e:
        print(f"❌ データ抽出エラー: {e}")
        return None

def process_csv_with_config_analysis(csv_file_path):
    """
    CSVファイルを処理して、設定に基づく利益商品を抽出
    """
    try:
        # 設定を読み込み
        config = load_config()
        
        # CSVファイルを読み込み
        df = pd.read_csv(csv_file_path, encoding='utf-8')
        print(f"📁 CSVファイル読み込み: {len(df)}行")
        print(f"📋 列名: {list(df.columns)}")
        
        # 結果用のDataFrameを準備
        result_df = df.copy()
        
        # eBayヘッダーを追加してE, F, G, H, I, J列を設定
        result_df['eBay商品名'] = ''     # E列: eBay商品名
        result_df['eBayURL'] = ''        # F列: eBayURL
        result_df['eBay価格(USD)'] = ''  # G列: eBay価格（ドル）
        result_df['eBay価格(JPY)'] = ''  # H列: eBay価格（円換算）
        result_df['利益金額'] = ''       # I列: 利益金額
        result_df['利益判定'] = ''       # J列: 利益判定（OK or 空白）
        
        # ドライバーをセットアップ
        driver = setup_driver()
        if not driver:
            return None
        
        try:
            # eBay Seller Hubにアクセス
            print("🌐 eBay Seller Hubにアクセス中...")
            driver.get("https://www.ebay.com/sh/research?marketplace=EBAY-US&tabName=SOLD")
            
            # 手動ログインを待機
            wait_for_manual_login(driver)
            
            # 各行を処理
            for index, row in df.iterrows():
                try:
                    print(f"\n🔄 処理中: {index+1}/{len(df)}")
                    
                    # 商品名から型番を抽出（列名に対応）
                    if 'title' in df.columns:
                        product_name = str(row['title'])
                    elif 'A' in df.columns:
                        product_name = str(row['A'])
                    else:
                        product_name = str(row.iloc[0])
                    
                    # メルカリ価格を取得（3列目）
                    if 'price' in df.columns:
                        mercari_price_text = str(row['price'])
                    elif 'C' in df.columns:
                        mercari_price_text = str(row['C'])
                    else:
                        mercari_price_text = str(row.iloc[2])
                    
                    mercari_price = parse_price(mercari_price_text)
                    minimum_ebay_price = calculate_minimum_ebay_price(mercari_price, config)
                    
                    print(f"📝 商品名: {product_name}")
                    print(f"💰 メルカリ価格: ¥{mercari_price:,.0f}")
                    print(f"📈 必要eBay価格: ¥{minimum_ebay_price:,.0f} (利益率{config['profit_calculation']['markup_rate']*100:.1f}% + 固定¥{config['profit_calculation']['fixed_profit']:,})")
                    
                    model_numbers = extract_model_numbers(product_name)
                    
                    if not model_numbers:
                        print(f"⚠️ 型番が見つかりません: {product_name}")
                        continue
                    
                    # 最初の型番を使用
                    model_number = model_numbers[0]
                    print(f"🎯 抽出された型番: {model_number}")
                    
                    # 型番を検索
                    if search_model_number(driver, model_number):
                        # 設定に基づく最高価格の利益商品を抽出
                        highest_product = extract_highest_price_product(driver, model_number, mercari_price, config)
                        
                        if highest_product:
                            # 利益金額を計算
                            profit_amount = highest_product['price_numeric'] - mercari_price
                            
                            # 最高価格商品データを結果に追加
                            result_df.at[index, 'eBay商品名'] = highest_product['item_name']
                            result_df.at[index, 'eBayURL'] = highest_product['item_url']
                            result_df.at[index, 'eBay価格(USD)'] = highest_product['price']
                            result_df.at[index, 'eBay価格(JPY)'] = f"¥{highest_product['price_numeric']:,.0f}"
                            result_df.at[index, '利益金額'] = f"¥{profit_amount:,.0f}"
                            result_df.at[index, '利益判定'] = 'OK'  # 利益が出る場合はOK
                            
                            print(f"✅ 設定条件クリア商品データ取得成功: {highest_product['item_name'][:30]}...")
                            print(f"   価格: {highest_product['price']} (利益: ¥{profit_amount:,.0f})")
                        else:
                            print(f"⚠️ 設定条件を満たす商品が見つかりません: {model_number}")
                            # 利益が出ない場合は列を空白のまま
                    else:
                        print(f"❌ 検索失敗: {model_number}")
                    
                    # 次の検索まで少し待機
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"❌ 行処理エラー {index+1}: {e}")
                    continue
            
            # 結果をCSVファイルに保存
            output_filename = f"ebay_config_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            result_df.to_csv(output_filename, index=False, encoding='utf-8')
            print(f"\n💾 結果保存: {output_filename}")
            
            # 利益商品の統計を表示
            profit_count = len(result_df[result_df['利益判定'] == 'OK'])
            
            # 総利益金額を計算
            total_profit = 0
            for index, row in result_df.iterrows():
                if row['利益判定'] == 'OK' and row['利益金額']:
                    profit_text = str(row['利益金額']).replace('¥', '').replace(',', '')
                    try:
                        total_profit += float(profit_text)
                    except ValueError:
                        pass
            
            print(f"\n📊 設定ベース利益商品統計:")
            print(f"   📋 設定内容:")
            print(f"      利益率: {config['profit_calculation']['markup_rate']*100:.1f}%")
            print(f"      固定利益: ¥{config['profit_calculation']['fixed_profit']:,}")
            print(f"      為替レート: 1USD = ¥{config['exchange_rate']['fixed_rate']}")
            print(f"   📊 結果:")
            print(f"      総商品数: {len(df)}件")
            print(f"      利益商品: {profit_count}件")
            print(f"      利益率: {profit_count/len(df)*100:.1f}%")
            print(f"      総利益金額: ¥{total_profit:,.0f}")
            if profit_count > 0:
                print(f"      平均利益: ¥{total_profit/profit_count:,.0f}")
            
            return result_df
            
        finally:
            driver.quit()
            print("🔚 ブラウザを閉じました")
            
    except Exception as e:
        print(f"❌ CSVファイル処理エラー: {e}")
        return None

def main():
    """
    メイン処理
    """
    print("=" * 60)
    print("🎯 eBay Seller Hub設定対応版")
    print("⚙️ Config.yamlから利益計算設定を読み込み")
    print("=" * 60)
    
    # CSVファイルパスを入力
    csv_file_path = input("📁 CSVファイルのパスを入力してください: ").strip()
    
    if not os.path.exists(csv_file_path):
        print(f"❌ ファイルが見つかりません: {csv_file_path}")
        return
    
    # 処理実行
    result = process_csv_with_config_analysis(csv_file_path)
    
    if result is not None:
        print("\n✅ 処理完了！")
        print(f"📊 処理結果: {len(result)}行")
        print("\n💡 設定を変更したい場合は config/config.yaml を編集してください")
    else:
        print("\n❌ 処理に失敗しました")

if __name__ == "__main__":
    main() 