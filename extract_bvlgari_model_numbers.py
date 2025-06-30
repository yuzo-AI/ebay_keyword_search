#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ブルガリ時計の識別番号パターン抽出スクリプト
CSVファイルのタイトルからブルガリ時計の型番・識別番号を抽出します
"""

import re
import csv
import pandas as pd
from collections import Counter

def extract_bvlgari_model_numbers(csv_file):
    """
    ブルガリ時計の識別番号パターンを抽出
    """
    # ブルガリ時計の型番パターン（正規表現）
    patterns = {
        'BB系 (ブルガリブルガリ)': r'\bBB\d{2}[A-Z]{1,8}\b',
        'ST系 (ソロテンポ)': r'\bST\d{2}[A-Z]{1,8}\b',
        'BZ系 (ビーゼロワン)': r'\bBZ\d{2}[A-Z]{1,5}\b',
        'DG系 (ディアゴノ)': r'\bDG\d{2}[A-Z]{1,5}\b',
        'EG系 (エルゴン)': r'\bEG\d{2}[A-Z]{1,5}\b',
        'AL系 (アルミニウム)': r'\bAL\d{2}[A-Z]{1,5}\b',
        'RT系 (レッタンゴロ)': r'\bRT\d{2}[A-Z]{1,5}\b',
        'AA系 (アショーマ)': r'\bAA\d{2}[A-Z]{1,5}\b',
        'SQ系 (クアドラード)': r'\bSQ\d{2}[A-Z]{1,5}\b',
        'SD系 (ディアゴノスクーバ)': r'\bSD\d{2}[A-Z]{1,5}\b'
    }
    
    # CSVファイルを読み込み
    df = pd.read_csv(csv_file)
    
    # 結果格納用
    extracted_models = []
    model_counts = Counter()
    
    print("🔍 ブルガリ時計 識別番号パターン抽出結果")
    print("=" * 60)
    
    # 各行のタイトルから型番を抽出
    for index, row in df.iterrows():
        title = str(row['title'])
        row_models = []
        
        # 各パターンでマッチング
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, title, re.IGNORECASE)
            if matches:
                for match in matches:
                    match_upper = match.upper()
                    row_models.append({
                        'pattern_type': pattern_name,
                        'model_number': match_upper,
                        'title': title,
                        'price': row['price'],
                        'url': row['product_url']
                    })
                    model_counts[match_upper] += 1
        
        if row_models:
            extracted_models.extend(row_models)
    
    # 結果の表示
    print(f"\n📊 抽出された識別番号数: {len(extracted_models)}個")
    print(f"📊 ユニークな型番数: {len(model_counts)}個")
    
    # パターン別の集計
    pattern_summary = Counter()
    for model in extracted_models:
        pattern_summary[model['pattern_type']] += 1
    
    print("\n📈 パターン別集計:")
    for pattern, count in pattern_summary.most_common():
        print(f"  {pattern}: {count}個")
    
    # 頻出型番TOP10
    print("\n🏆 頻出型番 TOP10:")
    for model, count in model_counts.most_common(10):
        print(f"  {model}: {count}回")
    
    # CSVファイルに保存
    output_file = 'bvlgari_model_numbers_extracted.csv'
    df_output = pd.DataFrame(extracted_models)
    df_output.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n💾 結果を保存しました: {output_file}")
    
    # ユニークな型番一覧を保存
    unique_models_file = 'bvlgari_unique_models.csv'
    unique_models = []
    for model, count in model_counts.most_common():
        # 該当する最初のエントリから詳細情報を取得
        for item in extracted_models:
            if item['model_number'] == model:
                unique_models.append({
                    'model_number': model,
                    'count': count,
                    'pattern_type': item['pattern_type'],
                    'example_title': item['title'][:100] + '...' if len(item['title']) > 100 else item['title'],
                    'example_price': item['price']
                })
                break
    
    df_unique = pd.DataFrame(unique_models)
    df_unique.to_csv(unique_models_file, index=False, encoding='utf-8-sig')
    print(f"💾 ユニーク型番一覧を保存しました: {unique_models_file}")
    
    return extracted_models, model_counts

def analyze_pattern_details(extracted_models):
    """
    抽出されたパターンの詳細分析
    """
    print("\n" + "=" * 60)
    print("🔬 詳細パターン分析")
    print("=" * 60)
    
    # パターン別の詳細分析
    pattern_details = {}
    for model in extracted_models:
        pattern = model['pattern_type']
        model_num = model['model_number']
        
        if pattern not in pattern_details:
            pattern_details[pattern] = []
        pattern_details[pattern].append(model_num)
    
    # 各パターンの分析結果
    for pattern, models in pattern_details.items():
        unique_models = list(set(models))
        print(f"\n📋 {pattern}:")
        print(f"  総数: {len(models)}個, ユニーク: {len(unique_models)}個")
        print(f"  型番例: {', '.join(unique_models[:5])}")
        if len(unique_models) > 5:
            print(f"  ...他{len(unique_models)-5}個")

if __name__ == "__main__":
    csv_file = "bvlgari watch_mercari copy.csv"
    
    try:
        extracted_models, model_counts = extract_bvlgari_model_numbers(csv_file)
        analyze_pattern_details(extracted_models)
        
        print("\n" + "=" * 60)
        print("✅ 抽出完了！")
        print("📁 出力ファイル:")
        print("  - bvlgari_model_numbers_extracted.csv (全データ)")
        print("  - bvlgari_unique_models.csv (ユニーク型番一覧)")
        print("=" * 60)
        
    except FileNotFoundError:
        print(f"❌ エラー: ファイル '{csv_file}' が見つかりません。")
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}") 