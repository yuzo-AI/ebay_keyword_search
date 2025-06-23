#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プロジェクトクリーンアップスクリプト
不要なファイルを安全に削除してプロジェクトを整理します
"""

import os
import glob
import shutil
from datetime import datetime

def create_backup():
    """
    削除前にバックアップを作成
    """
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"📦 バックアップ作成中: {backup_dir}")
    
    # 削除対象ファイルをバックアップ
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    return backup_dir

def cleanup_old_scripts():
    """
    古いバージョンのスクリプトを削除
    """
    old_scripts = [
        "extract_ebay_data.py",
        "extract_ebay_data_simple.py", 
        "extract_ebay_data_stable.py",
        "extract_ebay_seller_hub_debug.py",
        "extract_ebay_seller_hub_fixed.py",
        "extract_ebay_seller_hub_final.py",
        "extract_ebay_seller_hub_login.py",
        "extract_ebay_seller_hub_profit.py",
        "extract_ebay_seller_hub_highest_price.py"
    ]
    
    deleted_count = 0
    for script in old_scripts:
        if os.path.exists(script):
            print(f"🗑️  削除: {script}")
            os.remove(script)
            deleted_count += 1
    
    print(f"✅ 古いスクリプト {deleted_count}個を削除")

def cleanup_html_files():
    """
    大量のHTMLデバッグファイルを削除
    """
    html_patterns = [
        "seller_hub_highest_*.html",
        "debug_page_*.html"
    ]
    
    deleted_count = 0
    total_size = 0
    
    for pattern in html_patterns:
        files = glob.glob(pattern)
        for file in files:
            if os.path.exists(file):
                size = os.path.getsize(file)
                total_size += size
                print(f"🗑️  削除: {file} ({size/1024/1024:.1f}MB)")
                os.remove(file)
                deleted_count += 1
    
    print(f"✅ HTMLファイル {deleted_count}個を削除 ({total_size/1024/1024:.1f}MB削減)")

def cleanup_result_files():
    """
    古い結果CSVファイルを削除
    """
    result_patterns = [
        "ebay_search_results_*.csv",
        "ebay_final_results_*.csv", 
        "ebay_profit_results_*.csv",
        "ebay_highest_price_results_*.csv"
    ]
    
    deleted_count = 0
    for pattern in result_patterns:
        files = glob.glob(pattern)
        for file in files:
            if os.path.exists(file):
                print(f"🗑️  削除: {file}")
                os.remove(file)
                deleted_count += 1
    
    print(f"✅ 結果ファイル {deleted_count}個を削除")

def cleanup_duplicate_files():
    """
    重複・不要ファイルを削除
    """
    duplicate_files = [
        "grand seiko_mercari - コピー.csv",
        "grand seiko_mercari_20.csv",
        "sample_data.csv",
        "SEARCH_INPUT_UPDATES.md"
    ]
    
    deleted_count = 0
    for file in duplicate_files:
        if os.path.exists(file):
            print(f"🗑️  削除: {file}")
            os.remove(file)
            deleted_count += 1
    
    print(f"✅ 重複ファイル {deleted_count}個を削除")

def cleanup_src_directory():
    """
    使用されていないsrcディレクトリを削除
    """
    if os.path.exists("src"):
        print("🗑️  削除: src/ ディレクトリ全体")
        shutil.rmtree("src")
        print("✅ srcディレクトリを削除")

def cleanup_html_directory():
    """
    htmlディレクトリの不要ファイルを削除（必要最小限を保持）
    """
    keep_files = ["After_search.html", "After_login.html"]
    
    if os.path.exists("html"):
        files = os.listdir("html")
        deleted_count = 0
        
        for file in files:
            if file not in keep_files:
                file_path = os.path.join("html", file)
                print(f"🗑️  削除: html/{file}")
                os.remove(file_path)
                deleted_count += 1
        
        print(f"✅ htmlディレクトリ内 {deleted_count}個のファイルを削除")

def show_summary():
    """
    クリーンアップ後のファイル構成を表示
    """
    print("\n" + "="*60)
    print("🎯 クリーンアップ完了！残存ファイル構成:")
    print("="*60)
    
    important_files = [
        "📁 設定・実行ファイル:",
        "  ✅ extract_ebay_seller_hub_config.py  # メインスクリプト",
        "  ✅ main.py                           # 従来版（参考）",
        "  ✅ config/config.yaml                # 設定ファイル",
        "",
        "📁 データファイル:",
        "  ✅ grand seiko_mercari.csv           # 実データ",
        "  ✅ requirements.txt                  # 依存関係",
        "",
        "📁 ドキュメント:",
        "  ✅ README.md                         # 使用方法",
        "  ✅ 要件定義.yaml                     # 要件定義",
        "",
        "📁 参考用HTML:",
        "  ✅ html/After_search.html            # セレクター参考",
        "  ✅ html/After_login.html             # ログイン参考"
    ]
    
    for line in important_files:
        print(line)
    
    print("\n💡 今後の実行は以下のコマンドで:")
    print("   python extract_ebay_seller_hub_config.py")

def main():
    """
    メイン処理
    """
    print("🧹 プロジェクトクリーンアップ開始")
    print("=" * 50)
    
    # 確認
    response = input("⚠️  不要ファイルを削除しますか？ (y/N): ")
    if response.lower() != 'y':
        print("❌ クリーンアップをキャンセルしました")
        return
    
    # バックアップ作成確認
    backup_response = input("📦 削除前にバックアップを作成しますか？ (Y/n): ")
    if backup_response.lower() != 'n':
        backup_dir = create_backup()
    
    print("\n🗑️  クリーンアップ実行中...")
    
    # 各種クリーンアップ実行
    cleanup_old_scripts()
    cleanup_html_files()
    cleanup_result_files()
    cleanup_duplicate_files()
    cleanup_src_directory()
    cleanup_html_directory()
    
    # サマリー表示
    show_summary()
    
    print(f"\n🎉 クリーンアップ完了！")
    print(f"💾 プロジェクトサイズが大幅に削減されました")

if __name__ == "__main__":
    main() 