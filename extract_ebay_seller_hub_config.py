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
        
        # 金額フィルター設定の表示
        price_filter = config.get('ebay', {}).get('price_filter', {})
        if price_filter.get('enable_price_filter', False):
            min_price = price_filter.get('min_price', 0)
            max_price = price_filter.get('max_price', 0)
            print(f"💰 金額フィルター: ${min_price} - ${max_price} (有効)")
        else:
            print(f"💰 金額フィルター: 無効")
        
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
        # OMEGA専用パターン
        r'\b\d{3}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{3}\b',  # OMEGA長型番 (例: 210.30.42.20.03.001)
        r'\b\d{4}\.\d{2}\.\d{2}\b',                        # OMEGA標準型番 (例: 1504.35.00)
        r'\b\d{3,4}\.\d{2}\b',                             # OMEGAシンプル型番 (例: 3592.50, 1504.35)
        r'\b\d{3}\.\d{3}\b',                               # OMEGAヴィンテージ (例: 566.002)
        r'(?:cal\.?\s*|Cal\.?\s*|CAL\.?\s*)(\d{3,4})\b',  # キャリバー番号 (例: cal.484, Cal.1030)
        r'\bSO33M\d{3}\b',                                 # スウォッチコラボ (例: SO33M100)
        
        # 既存パターン
        r'\b[A-Z]{2,4}[0-9]{3,4}[A-Z]?\b',  # 腕時計型番 (例: SBGX263, SBGA211)
        r'\b[0-9]{4}-[0-9]{4}\b',           # ハイフン付き型番 (例: 5645-7010)
        r'\b[A-Z]{1,2}[0-9]{3,6}[A-Z]?\b', # 家電型番 (例: KJ55X8500G)
        r'\b[0-9]{3,6}[A-Z]{2,4}\b',       # 数字+文字型番
        
        # OMEGA用追加パターン（数字のみ）
        r'\b\d{4}\b(?=.*(?:OMEGA|オメガ|De\s*Ville|デビル))',  # De Ville系4桁 (例: 1377, 1458)
        r'\b03-\d{8}\b',                                      # 特殊番号 (例: 03-24010802)
    ]
    
    found_models = []
    for pattern in patterns:
        # キャリバー番号の場合は特別処理
        if 'cal' in pattern.lower():
            matches = re.findall(pattern, text, re.IGNORECASE)
            # キャリバー番号の場合は数字部分のみを抽出
            for match in matches:
                if match:
                    found_models.append(f"Cal.{match}")
        else:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_models.extend(matches)
    
    # 重複を除去し、結果を返す
    unique_models = list(set(found_models))
    
    # デバッグ用：抽出された型番を表示
    if unique_models:
        print(f"  🔍 抽出された型番: {', '.join(unique_models)}")
    
    return unique_models

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
    time.sleep(2)  # 3秒から2秒に短縮

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
        time.sleep(0.2)  # クリア処理の完了を待機（0.5→0.2秒に短縮）
        
        # Ctrl+A → Delete で確実にクリア
        search_input.send_keys(Keys.CONTROL + "a")
        search_input.send_keys(Keys.DELETE)
        
        # 型番を入力
        search_input.send_keys(model_number)
        time.sleep(0.3)  # 1秒から0.3秒に短縮
        
        # 入力内容を確認（デバッグ用）
        current_value = search_input.get_attribute('value')
        print(f"🔍 検索窓の内容確認: '{current_value}'")
        
        # Enterキーで検索実行
        search_input.send_keys(Keys.RETURN)
        print(f"🔍 検索実行: {model_number}")
        
        # 検索結果の読み込みを動的に待機
        print("⏳ 検索結果の読み込み待機中...")
        try:
            # テーブル行が表示されるまで最大5秒待機
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tr.research-table-row"))
            )
            time.sleep(1)  # 追加の読み込み時間を短縮
        except TimeoutException:
            # テーブルが見つからない場合も続行
            time.sleep(2)
        
        return True
        
    except Exception as e:
        print(f"❌ 検索エラー: {e}")
        return False

def apply_price_filter_if_enabled(driver, config):
    """
    設定に基づいて価格フィルターを適用（有効な場合のみ）
    """
    # 価格フィルターが有効かチェック
    price_filter_enabled = config.get('ebay', {}).get('price_filter', {}).get('enable_price_filter', False)
    
    if not price_filter_enabled:
        print("📊 価格フィルターは無効です（config.yamlで設定）")
        return True
    
    min_price = config.get('ebay', {}).get('price_filter', {}).get('min_price', 0)
    max_price = config.get('ebay', {}).get('price_filter', {}).get('max_price', 999999)
    
    print(f"💰 金額フィルターを適用中: ${min_price} - ${max_price}")
    
    try:
        # まず最初にSoldタブをクリック（フィルター適用前に）
        print("🔄 Soldタブを先にクリック中...")
        sold_tab_clicked = False
        
        # JavaScriptでSoldタブを探してクリック
        try:
            script = """
            var elements = document.querySelectorAll('span, button, a, div[role="tab"]');
            for (var i = 0; i < elements.length; i++) {
                var elem = elements[i];
                if (elem.textContent.trim() === 'Sold' || 
                    elem.textContent.trim() === '"Sold"' ||
                    (elem.getAttribute('aria-label') && elem.getAttribute('aria-label').includes('Sold'))) {
                    return elem;
                }
            }
            return null;
            """
            sold_tab = driver.execute_script(script)
            
            if sold_tab:
                driver.execute_script("arguments[0].click();", sold_tab)
                print("✅ Soldタブをクリックしました")
                sold_tab_clicked = True
                
                # Soldタブクリック後の読み込み待機
                time.sleep(3)
                
                # テーブルが再読み込みされるのを待機
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "tr.research-table-row"))
                    )
                    print("✅ Soldタブのデータ読み込み完了")
                except TimeoutException:
                    print("⚠️ Soldタブのデータ読み込みタイムアウト")
            else:
                print("⚠️ Soldタブが見つかりません")
                
        except Exception as e:
            print(f"❌ Soldタブクリックエラー: {e}")
        
        # Soldタブが有効になったことを確認
        final_url = driver.current_url
        if "tabName=SOLD" in final_url:
            print("✅ SOLDタブが有効です（URL確認）")
        else:
            print("⚠️ URLにSOLDタブパラメータが見つかりません")
        
        # 少し待機してから価格フィルターを適用
        time.sleep(2)
        
        # Price filterボタンを探してクリック
        print("🔍 Price filterボタンを探しています...")
        try:
            # JavaScript経由でPrice filterボタンを探す
            script = """
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var button = buttons[i];
                var text = button.textContent || button.innerText;
                if (text && text.includes('Price filter')) {
                    return button;
                }
            }
            return null;
            """
            price_filter_button = driver.execute_script(script)
            
            if not price_filter_button:
                raise Exception("Price filterボタンが見つかりません")
            
            # ボタンを表示してクリック
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", price_filter_button)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", price_filter_button)
            print("✅ Price filterボタンをクリック")
            time.sleep(1)
        except Exception as e:
            print(f"❌ Price filterボタンクリックエラー: {e}")
            return False
        
        # 最小価格入力欄を探して入力（新しいIDセレクターを追加）
        min_price_selectors = [
            "#s0-1-0-0-22-2-10-13-3-16-2-0-0-1-6-2-23-0-0-10-24-1-5-0-3-textbox",  # 提供されたID
            "input[aria-label='min price filter']",  # aria-labelから特定
            "input[placeholder='$']",  # placeholderから特定
            "input[placeholder*='Min']",
            "input[aria-label*='minimum']",
            "input[name*='min']"
        ]
        
        min_price_input = None
        for selector in min_price_selectors:
            try:
                min_price_input = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"✅ 最小価格入力欄発見: {selector}")
                break
            except TimeoutException:
                continue
        
        if min_price_input:
            try:
                # JavaScriptで直接値を設定する方法も試す
                driver.execute_script("arguments[0].value = '';", min_price_input)
                driver.execute_script(f"arguments[0].value = '{min_price}';", min_price_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", min_price_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", min_price_input)
                print(f"✅ 最小価格入力: ${min_price}")
                time.sleep(0.3)  # 1秒から0.3秒に短縮
            except Exception as e:
                print(f"❌ 最小価格入力エラー: {e}")
        
        # 最大価格入力欄を探して入力（新しいIDセレクターを追加）
        max_price_selectors = [
            "#s0-1-0-0-22-2-10-13-3-16-2-0-0-1-6-2-23-0-0-10-24-1-5-0-5-textbox",  # 提供されたID
            "input[aria-label='max price filter']",  # aria-labelから特定
            "input[placeholder='$$']",  # placeholderから特定（2つの$）
            "input[placeholder*='Max']",
            "input[aria-label*='maximum']",
            "input[name*='max']"
        ]
        
        max_price_input = None
        for selector in max_price_selectors:
            try:
                max_price_input = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"✅ 最大価格入力欄発見: {selector}")
                break
            except TimeoutException:
                continue
        
        if max_price_input:
            try:
                # JavaScriptで直接値を設定する方法も試す
                driver.execute_script("arguments[0].value = '';", max_price_input)
                driver.execute_script(f"arguments[0].value = '{max_price}';", max_price_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", max_price_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", max_price_input)
                print(f"✅ 最大価格入力: ${max_price}")
                time.sleep(0.3)  # 1秒から0.3秒に短縮
            except Exception as e:
                print(f"❌ 最大価格入力エラー: {e}")
        
        # 入力完了後、少し待機してApplyボタンが有効になるのを待つ
        time.sleep(2)  # 1秒から2秒に延長
        print("🔍 Applyボタンを探しています...")
        
        # まず全てのボタンをデバッグ表示
        try:
            debug_script = """
            var buttons = document.querySelectorAll('button');
            var buttonInfo = [];
            for (var i = 0; i < buttons.length; i++) {
                var btn = buttons[i];
                buttonInfo.push({
                    text: btn.textContent.trim(),
                    className: btn.className,
                    enabled: !btn.disabled,
                    visible: btn.offsetParent !== null
                });
            }
            return buttonInfo;
            """
            all_buttons = driver.execute_script(debug_script)
            print(f"🔍 ページ上の全ボタン数: {len(all_buttons)}")
            
            # Applyテキストを含むボタンを探す
            apply_buttons = [btn for btn in all_buttons if 'apply' in btn['text'].lower()]
            print(f"🔍 'Apply'テキストを含むボタン: {len(apply_buttons)}")
            for btn in apply_buttons:
                print(f"  📋 ボタン: '{btn['text']}' - 有効: {btn['enabled']}, 表示: {btn['visible']}")
        except Exception as e:
            print(f"⚠️ ボタンデバッグエラー: {e}")
        
        # Applyボタンを探してクリック（より包括的な検索）
        apply_button_clicked = False
        
        # 改善されたApplyボタン検索
        try:
            print("🔍 Applyボタンを検索中（改善版）...")
            
            # より包括的なJavaScript検索
            enhanced_script = """
            // 全てのボタンとdivを検索
            var allElements = document.querySelectorAll('button, div[role="button"], span[role="button"], a[role="button"]');
            var candidates = [];
            
            for (var i = 0; i < allElements.length; i++) {
                var elem = allElements[i];
                var text = elem.textContent || elem.innerText || '';
                var ariaLabel = elem.getAttribute('aria-label') || '';
                
                // 'Apply'テキストを含む要素を探す（大文字小文字区別なし）
                if (text.toLowerCase().includes('apply') || ariaLabel.toLowerCase().includes('apply')) {
                    candidates.push({
                        element: elem,
                        text: text.trim(),
                        className: elem.className,
                        enabled: !elem.disabled,
                        visible: elem.offsetParent !== null,
                        tagName: elem.tagName
                    });
                }
            }
            
            // 最も適切なApplyボタンを選択
            var bestCandidate = null;
            for (var j = 0; j < candidates.length; j++) {
                var candidate = candidates[j];
                
                // 'Apply'のみのテキストを優先
                if (candidate.text.toLowerCase() === 'apply' && candidate.enabled && candidate.visible) {
                    bestCandidate = candidate.element;
                    break;
                }
            }
            
            // 見つからない場合は、有効で表示されている最初の候補を選択
            if (!bestCandidate) {
                for (var k = 0; k < candidates.length; k++) {
                    if (candidates[k].enabled && candidates[k].visible) {
                        bestCandidate = candidates[k].element;
                        break;
                    }
                }
            }
            
            return {
                found: bestCandidate !== null,
                element: bestCandidate,
                candidates: candidates.length
            };
            """
            
            search_result = driver.execute_script(enhanced_script)
            
            if search_result['found']:
                apply_button = search_result['element']
                print(f"✅ Applyボタン発見（{search_result['candidates']}個の候補から選択）")
                
                # ボタンの詳細情報を表示
                button_info = driver.execute_script("""
                return {
                    text: arguments[0].textContent.trim(),
                    className: arguments[0].className,
                    enabled: !arguments[0].disabled,
                    visible: arguments[0].offsetParent !== null,
                    tagName: arguments[0].tagName
                };
                """, apply_button)
                
                print(f"📋 選択されたボタン: '{button_info['text']}' ({button_info['tagName']}) - 有効: {button_info['enabled']}, 表示: {button_info['visible']}")
                
                # ボタンをスクロールして表示
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", apply_button)
                time.sleep(1)
                
                # クリック試行
                click_success = False
                
                # 方法1: 通常のクリック
                try:
                    apply_button.click()
                    print("✅ Applyボタンクリック成功（通常クリック）")
                    click_success = True
                except Exception as e:
                    print(f"⚠️ 通常クリック失敗: {e}")
                
                # 方法2: JavaScriptクリック
                if not click_success:
                    try:
                        driver.execute_script("arguments[0].click();", apply_button)
                        print("✅ Applyボタンクリック成功（JavaScriptクリック）")
                        click_success = True
                    except Exception as e:
                        print(f"⚠️ JavaScriptクリック失敗: {e}")
                
                # 方法3: フォーカス + Enter
                if not click_success:
                    try:
                        driver.execute_script("arguments[0].focus();", apply_button)
                        apply_button.send_keys(Keys.RETURN)
                        print("✅ Applyボタンクリック成功（Enter押下）")
                        click_success = True
                    except Exception as e:
                        print(f"⚠️ Enter押下失敗: {e}")
                
                if click_success:
                    apply_button_clicked = True
                    print("🎉 Applyボタンのクリックに成功しました！")
                else:
                    print("❌ 全てのクリック方法が失敗しました")
                    
            else:
                print(f"❌ Applyボタンが見つかりません（{search_result['candidates']}個の候補を検索）")
                
        except Exception as e:
            print(f"❌ 改善版Applyボタン検索エラー: {e}")
        
        if apply_button_clicked:
            # フィルター適用のため待機時間を延長
            print("⏳ フィルター適用中...")
            time.sleep(5)  # 3秒から5秒に延長
            
            # フィルター適用確認のため、ページを再読み込み待機
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.research-table-row"))
                )
                print("✅ フィルター適用後のデータ読み込み完了")
            except TimeoutException:
                print("⚠️ フィルター適用後のデータ読み込みタイムアウト")
        else:
            print("❌ Applyボタンのクリックに失敗しました")
        
        print(f"💰 金額フィルター適用完了: ${min_price} - ${max_price}")
        
        # フィルター適用の確認（現在のページURLをチェック）
        current_url = driver.current_url
        if "minPrice" in current_url or "maxPrice" in current_url:
            print("✅ URLにフィルターパラメータが含まれています")
        else:
            print("⚠️ URLにフィルターパラメータが見つかりません")
        
        # フィルターが適用されたか最終確認（現在の表示内容を確認）
        try:
            # フィルター適用後の価格を確認
            script_check = """
            var prices = document.querySelectorAll('td.research-table-row__avgSoldPrice, td.research-table-row__soldPrice');
            var priceValues = [];
            for (var i = 0; i < prices.length && i < 5; i++) {
                var text = prices[i].textContent;
                var match = text.match(/\\$([\\d,]+\\.?\\d*)/);
                if (match) {
                    priceValues.push(parseFloat(match[1].replace(',', '')));
                }
            }
            return priceValues;
            """
            detected_prices = driver.execute_script(script_check)
            if detected_prices:
                print(f"🔍 フィルター適用後の価格サンプル: {[f'${p:.2f}' for p in detected_prices[:3]]}")
                # 全ての価格がフィルター範囲外の場合は警告
                out_of_range = [p for p in detected_prices if p < min_price or p > max_price]
                if out_of_range:
                    print(f"⚠️ 警告: フィルター範囲外の価格を検出: {[f'${p:.2f}' for p in out_of_range]}")
                    # 範囲外の価格が多い場合は、フィルターが適用されていない可能性
                    if len(out_of_range) > len(detected_prices) * 0.5:
                        print("❌ フィルターが正しく適用されていない可能性があります")
        except Exception as e:
            print(f"⚠️ 価格確認エラー: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 金額フィルター適用エラー: {e}")
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
        
        # 価格フィルターの設定を取得
        price_filter_enabled = config.get('ebay', {}).get('price_filter', {}).get('enable_price_filter', False)
        min_filter_price = config.get('ebay', {}).get('price_filter', {}).get('min_price', 0)
        max_filter_price = config.get('ebay', {}).get('price_filter', {}).get('max_price', 999999)
        
        # デバッグ用HTMLを取得（保存はしない）
        html_content = driver.page_source
        
        # デバッグ用: 特定の型番の場合はHTMLを保存
        if model_number in ['SBGX005', 'SARB033', '9940-8000']:
            debug_filename = f"debug_{model_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(debug_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  📝 デバッグHTML保存: {debug_filename}")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # research-table-row全体を取得してデータを組み合わせ
        table_rows = soup.find_all('tr', class_='research-table-row')
        print(f"📋 テーブル行: {len(table_rows)}件")
        
        # 全ての価格を収集してフィルターの動作を確認
        all_prices = []
        
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
            
            # 価格（売れた価格を取得）- 複数のセレクターを試す
            price_found = False
            
            # まず個別の販売価格を探す
            individual_price_selectors = [
                ('td', 'research-table-row__soldPrice'),
                ('td', 'research-table-row__price'),
                ('span', 'item-price'),
                ('div', 'item-price-sold')
            ]
            
            for tag, class_name in individual_price_selectors:
                price_element = row.find(tag, class_=class_name)
                if price_element:
                    price_text = price_element.get_text(strip=True)
                    # 価格から数値部分を抽出
                    price_match = re.search(r'\$[\d,]+\.?\d*', price_text)
                    if price_match:
                        product['price'] = price_match.group()
                        usd_price = parse_price(price_match.group())
                        jpy_price = usd_price * exchange_rate
                        product['usd_price'] = usd_price
                        product['price_numeric'] = jpy_price
                        price_found = True
                        print(f"  💵 個別価格発見: ${usd_price:.2f} (セレクター: {tag}.{class_name})")
                        break
            
            # 個別価格が見つからない場合は平均価格を使用
            if not price_found:
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
                            print(f"  📊 平均価格使用: ${usd_price:.2f}")
                            price_found = True
            
            # 価格が正常に取得できた場合のみ処理を続行
            if price_found and product['usd_price'] > 0:
                # 価格を記録
                all_prices.append(product['usd_price'])
                
                # 価格フィルターのチェック（有効な場合）
                if price_filter_enabled:
                    if product['usd_price'] < min_filter_price or product['usd_price'] > max_filter_price:
                        print(f"  ⚠️ フィルター範囲外: ${product['usd_price']:.2f} (フィルター: ${min_filter_price}-${max_filter_price})")
                        continue  # フィルター範囲外はスキップ
                
                # 設定に基づく利益判定
                if product['price_numeric'] >= minimum_ebay_price:
                    product['is_profitable'] = True
                    actual_profit = product['price_numeric'] - mercari_price
                    print(f"  💰 利益商品発見: {product['item_name'][:30]}... - ${product['usd_price']:.2f} (¥{product['price_numeric']:,.0f}) 利益:¥{actual_profit:,.0f}")
            
            # 利益が出る商品のみ追加
            if product['is_profitable'] and any([product['item_name'], product['item_url'], product['price']]):
                profitable_products.append(product)
        
        # 価格の統計を表示
        if all_prices:
            print(f"📊 検出された価格の分布:")
            print(f"   最小価格: ${min(all_prices):.2f}")
            print(f"   最大価格: ${max(all_prices):.2f}")
            print(f"   価格数: {len(all_prices)}件")
            if price_filter_enabled:
                in_range = [p for p in all_prices if min_filter_price <= p <= max_filter_price]
                print(f"   フィルター範囲内: {len(in_range)}件 / {len(all_prices)}件")
        
        # 最高価格の商品を選択
        if profitable_products:
            # USD価格で並び替えて最高価格を取得
            highest_price_product = max(profitable_products, key=lambda x: x['usd_price'])
            
            # フィルター範囲内の商品のみを表示
            if price_filter_enabled:
                filtered_products = [p for p in profitable_products if min_filter_price <= p['usd_price'] <= max_filter_price]
                print(f"📊 フィルター適用後: {len(filtered_products)}件 / 全{len(profitable_products)}件")
                
                if filtered_products:
                    # フィルター範囲内の最高価格商品を選択
                    highest_price_product = max(filtered_products, key=lambda x: x['usd_price'])
                else:
                    print(f"⚠️ フィルター範囲内（${min_filter_price}-${max_filter_price}）に利益商品がありません")
                    return None
            
            print(f"✅ 最高価格商品選択: {len(profitable_products)}件中から選択")
            print(f"  🏆 最高価格: ${highest_price_product['usd_price']:.2f} (¥{highest_price_product['price_numeric']:,.0f})")
            print(f"  📝 商品名: {highest_price_product['item_name'][:50]}...")
            print(f"  💰 実際の利益: ¥{highest_price_product['price_numeric'] - mercari_price:,.0f}")
            
            # 最終確認：選択された商品がフィルター範囲内か
            if price_filter_enabled and (highest_price_product['usd_price'] < min_filter_price or highest_price_product['usd_price'] > max_filter_price):
                print(f"❌ エラー: 選択された商品がフィルター範囲外です！")
                return None
            
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
            
            # ログイン後、Soldタブが選択されているか確認
            print("🔄 初回Soldタブ確認中...")
            try:
                # 少し待機してからSoldタブを確認
                time.sleep(2)
                
                # JavaScriptでSoldタブがアクティブか確認
                script = """
                var tabs = document.querySelectorAll('[role="tab"], .tab-button, span');
                for (var i = 0; i < tabs.length; i++) {
                    if (tabs[i].textContent.includes('Sold') && 
                        (tabs[i].getAttribute('aria-selected') === 'true' || 
                         tabs[i].classList.contains('active') ||
                         tabs[i].classList.contains('selected'))) {
                        return true;
                    }
                }
                return false;
                """
                sold_tab_active = driver.execute_script(script)
                
                if not sold_tab_active:
                    # Soldタブがアクティブでない場合はクリック
                    script_click = """
                    var elements = document.querySelectorAll('span, button, a, div[role="tab"]');
                    for (var i = 0; i < elements.length; i++) {
                        var elem = elements[i];
                        if (elem.textContent.trim() === 'Sold' || 
                            elem.textContent.trim() === '"Sold"') {
                            elem.click();
                            return true;
                        }
                    }
                    return false;
                    """
                    if driver.execute_script(script_click):
                        print("✅ 初回Soldタブをクリックしました")
                        time.sleep(2)
                    else:
                        print("⚠️ 初回Soldタブのクリックに失敗しました")
                else:
                    print("✅ Soldタブは既にアクティブです")
                    
            except Exception as e:
                print(f"⚠️ 初回Soldタブ確認エラー: {e}")
            
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
                        # 金額フィルターを適用（設定で有効な場合）
                        apply_price_filter_if_enabled(driver, config)
                        
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
                    
                    # 次の検索まで少し待機（連続検索によるブロックを避ける）
                    time.sleep(1)  # 2秒から1秒に短縮
                    
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