#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汎用時計識別番号パターン抽出スクリプト
CSVファイルのタイトルから複数ブランドの時計の型番・識別番号を抽出します
対応ブランド: BVLGARI, Grand Seiko
"""

import re
import csv
import pandas as pd
from collections import Counter
import argparse
import os

class WatchModelExtractor:
    def __init__(self):
        """
        時計ブランドの型番パターンを定義
        """
        self.brand_patterns = {
            'BVLGARI': {
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
            },
            'GRAND_SEIKO': {
                'SBGX系 (クオーツ)': r'\bSBGX\d{3}\b',
                'SBGA系 (スプリングドライブ)': r'\bSBGA\d{3}\b',
                'SBGR系 (メカニカル)': r'\bSBGR\d{3}\b',
                'SBGT系 (GMT)': r'\bSBGT\d{3}\b',
                'SBGN系 (スポーツ)': r'\bSBGN\d{3}\b',
                'SBGC系 (クロノグラフ)': r'\bSBGC\d{3}\b',
                'SBGW系 (エレガンス)': r'\bSBGW\d{3}\b',
                'SBGJ系 (GMT)': r'\bSBGJ\d{3}\b',
                'SBGE系 (スプリングドライブGMT)': r'\bSBGE\d{3}\b',
                'SBGV系 (ビンテージ)': r'\bSBGV\d{3}\b',
                'SBGP系 (プレミア)': r'\bSBGP\d{3}\b',
                'SBGH系 (ヘリテージ)': r'\bSBGH\d{3}\b'
            }
        }
    
    def detect_brand(self, csv_file):
        """
        CSVファイルの内容からブランドを自動検出
        """
        try:
            df = pd.read_csv(csv_file, nrows=10)  # 最初の10行だけチェック
            sample_text = ' '.join(df['title'].astype(str).tolist()).upper()
            
            bvlgari_keywords = ['BVLGARI', 'ブルガリ', 'BULGARI']
            seiko_keywords = ['GRAND SEIKO', 'グランドセイコー', 'SBGX', 'SBGA', 'SBGR']
            
            bvlgari_count = sum(1 for keyword in bvlgari_keywords if keyword in sample_text)
            seiko_count = sum(1 for keyword in seiko_keywords if keyword in sample_text)
            
            if bvlgari_count > seiko_count:
                return 'BVLGARI'
            elif seiko_count > bvlgari_count:
                return 'GRAND_SEIKO'
            else:
                return 'BOTH'  # 両方検出された場合
                
        except Exception as e:
            print(f"⚠️ ブランド自動検出エラー: {e}")
            return 'BOTH'
    
    def extract_model_numbers(self, csv_file, target_brands=None, output_prefix=None):
        """
        指定されたブランドの識別番号パターンを抽出
        """
        # ブランドの自動検出
        if target_brands is None:
            detected_brand = self.detect_brand(csv_file)
            if detected_brand == 'BOTH':
                target_brands = ['BVLGARI', 'GRAND_SEIKO']
            else:
                target_brands = [detected_brand]
        
        # CSVファイルを読み込み
        df = pd.read_csv(csv_file)
        
        # 結果格納用
        extracted_models = []
        model_counts = Counter()
        brand_summary = {}
        
        print("🔍 汎用時計識別番号パターン抽出結果")
        print("=" * 60)
        print(f"📁 対象ファイル: {csv_file}")
        print(f"🏷️ 対象ブランド: {', '.join(target_brands)}")
        print("=" * 60)
        
        # 各ブランドのパターンを処理
        for brand in target_brands:
            if brand not in self.brand_patterns:
                print(f"⚠️ 未対応ブランド: {brand}")
                continue
                
            brand_models = []
            patterns = self.brand_patterns[brand]
            
            # 各行のタイトルから型番を抽出
            for index, row in df.iterrows():
                title = str(row['title'])
                
                # 各パターンでマッチング
                for pattern_name, pattern in patterns.items():
                    matches = re.findall(pattern, title, re.IGNORECASE)
                    if matches:
                        for match in matches:
                            match_upper = match.upper()
                            model_info = {
                                'brand': brand,
                                'pattern_type': pattern_name,
                                'model_number': match_upper,
                                'title': title,
                                'price': row['price'],
                                'url': row['product_url']
                            }
                            brand_models.append(model_info)
                            extracted_models.append(model_info)
                            model_counts[f"{brand}_{match_upper}"] += 1
            
            brand_summary[brand] = len(brand_models)
        
        # 結果の表示
        print(f"\n📊 抽出された識別番号数: {len(extracted_models)}個")
        print(f"📊 ユニークな型番数: {len(model_counts)}個")
        
        # ブランド別の集計
        print(f"\n🏷️ ブランド別集計:")
        for brand, count in brand_summary.items():
            print(f"  {brand}: {count}個")
        
        # パターン別の集計
        pattern_summary = Counter()
        for model in extracted_models:
            pattern_key = f"{model['brand']}_{model['pattern_type']}"
            pattern_summary[pattern_key] += 1
        
        print("\n📈 パターン別集計:")
        for pattern, count in pattern_summary.most_common():
            print(f"  {pattern}: {count}個")
        
        # 頻出型番TOP15
        print("\n🏆 頻出型番 TOP15:")
        for model_key, count in model_counts.most_common(15):
            brand, model = model_key.split('_', 1)
            print(f"  {brand} {model}: {count}回")
        
        # ファイル名のプレフィックス設定
        if output_prefix is None:
            output_prefix = os.path.splitext(os.path.basename(csv_file))[0]
        
        # CSVファイルに保存
        output_file = f'{output_prefix}_model_numbers_extracted.csv'
        df_output = pd.DataFrame(extracted_models)
        df_output.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n💾 結果を保存しました: {output_file}")
        
        # ユニークな型番一覧を保存
        unique_models_file = f'{output_prefix}_unique_models.csv'
        unique_models = []
        for model_key, count in model_counts.most_common():
            brand, model = model_key.split('_', 1)
            # 該当する最初のエントリから詳細情報を取得
            for item in extracted_models:
                if item['brand'] == brand and item['model_number'] == model:
                    unique_models.append({
                        'brand': brand,
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
        
        return extracted_models, model_counts, brand_summary
    
    def analyze_pattern_details(self, extracted_models):
        """
        抽出されたパターンの詳細分析
        """
        print("\n" + "=" * 60)
        print("🔬 詳細パターン分析")
        print("=" * 60)
        
        # ブランド別・パターン別の詳細分析
        brand_pattern_details = {}
        for model in extracted_models:
            brand = model['brand']
            pattern = model['pattern_type']
            model_num = model['model_number']
            
            if brand not in brand_pattern_details:
                brand_pattern_details[brand] = {}
            if pattern not in brand_pattern_details[brand]:
                brand_pattern_details[brand][pattern] = []
            brand_pattern_details[brand][pattern].append(model_num)
        
        # 各ブランド・パターンの分析結果
        for brand, patterns in brand_pattern_details.items():
            print(f"\n🏷️ 【{brand}】")
            for pattern, models in patterns.items():
                unique_models = list(set(models))
                print(f"  📋 {pattern}:")
                print(f"    総数: {len(models)}個, ユニーク: {len(unique_models)}個")
                print(f"    型番例: {', '.join(unique_models[:5])}")
                if len(unique_models) > 5:
                    print(f"    ...他{len(unique_models)-5}個")

def main():
    """
    メイン処理
    """
    parser = argparse.ArgumentParser(description='汎用時計識別番号抽出ツール')
    parser.add_argument('csv_file', help='入力CSVファイル')
    parser.add_argument('--brands', nargs='+', choices=['BVLGARI', 'GRAND_SEIKO'], 
                       help='対象ブランド (指定しない場合は自動検出)')
    parser.add_argument('--output-prefix', help='出力ファイルのプレフィックス')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.csv_file):
        print(f"❌ エラー: ファイル '{args.csv_file}' が見つかりません。")
        return
    
    extractor = WatchModelExtractor()
    
    try:
        extracted_models, model_counts, brand_summary = extractor.extract_model_numbers(
            args.csv_file, 
            target_brands=args.brands,
            output_prefix=args.output_prefix
        )
        
        extractor.analyze_pattern_details(extracted_models)
        
        print("\n" + "=" * 60)
        print("✅ 抽出完了！")
        print("📁 出力ファイル:")
        prefix = args.output_prefix or os.path.splitext(os.path.basename(args.csv_file))[0]
        print(f"  - {prefix}_model_numbers_extracted.csv (全データ)")
        print(f"  - {prefix}_unique_models.csv (ユニーク型番一覧)")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")

if __name__ == "__main__":
    # コマンドライン引数がない場合はデフォルトで実行
    import sys
    if len(sys.argv) == 1:
        # デフォルトでブルガリファイルを処理
        default_file = "bvlgari watch_mercari copy.csv"
        if os.path.exists(default_file):
            extractor = WatchModelExtractor()
            try:
                extracted_models, model_counts, brand_summary = extractor.extract_model_numbers(default_file)
                extractor.analyze_pattern_details(extracted_models)
                
                print("\n" + "=" * 60)
                print("✅ 抽出完了！")
                print("📁 出力ファイル:")
                print("  - bvlgari watch_mercari copy_model_numbers_extracted.csv (全データ)")
                print("  - bvlgari watch_mercari copy_unique_models.csv (ユニーク型番一覧)")
                print("=" * 60)
                
            except Exception as e:
                print(f"❌ エラーが発生しました: {e}")
        else:
            print(f"❌ エラー: デフォルトファイル '{default_file}' が見つかりません。")
            print("使用方法: python extract_watch_model_numbers_universal.py <CSVファイル> [--brands BVLGARI GRAND_SEIKO]")
    else:
        main() 