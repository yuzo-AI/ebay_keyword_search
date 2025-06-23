#!/usr/bin/env python3
"""
メルカリ-eBay価格比較ツール
Version: 1.0.0

メルカリCSVから型番を抽出し、eBay販売価格と比較して利益判定を行うツール
"""

import argparse
import sys
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from tqdm import tqdm

# プロジェクトのsrcディレクトリをパスに追加
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')

# パスが存在することを確認
if not os.path.exists(src_path):
    print(f"❌ srcディレクトリが見つかりません: {src_path}")
    sys.exit(1)

# sys.pathに追加（重複チェック付き）
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# パスの確認（デバッグモード）
DEBUG_MODE = True  # 本格運用時はFalseに
if DEBUG_MODE:
    print(f"🔍 Current directory: {current_dir}")
    print(f"🔍 Source path: {src_path}")
    print(f"🔍 Python path includes src: {src_path in sys.path}")

# srcディレクトリからのインポート
try:
    # まずモジュールの存在確認
    required_modules = [
        'config_loader', 'file_handler', 'model_extractor', 
        'price_processor', 'browser_controller', 'ebay_scraper', 'output_handler'
    ]
    
    missing_modules = []
    for module_name in required_modules:
        module_path = os.path.join(src_path, f"{module_name}.py")
        if not os.path.exists(module_path):
            missing_modules.append(module_name)
    
    if missing_modules:
        print(f"❌ 必要なモジュールが見つかりません: {missing_modules}")
        sys.exit(1)
    
    # 実際のインポート
    import config_loader
    import file_handler
    import model_extractor
    import price_processor
    import browser_controller
    import ebay_scraper
    import output_handler
    
    # クラスのインポート
    from config_loader import ConfigLoader, ConfigurationError
    from file_handler import CSVReader, CSVWriter
    from model_extractor import ModelExtractor, ModelExtractionError
    from price_processor import PriceCalculator, PriceCalculationError
    from browser_controller import BrowserController, SessionExpiredException, RateLimitException
    from ebay_scraper import EbayScraper, EbayAccessError
    from output_handler import OutputHandler
    
    if DEBUG_MODE:
        print("✅ All modules imported successfully")
    
except ImportError as e:
    print(f"❌ インポートエラー: {e}")
    print(f"❌ 詳細なエラー情報:")
    import traceback
    traceback.print_exc()
    
    print(f"\n❌ 診断情報:")
    print(f"   作業ディレクトリ: {os.getcwd()}")
    print(f"   srcパス: {src_path}")
    print(f"   srcパス存在: {os.path.exists(src_path)}")
    
    if os.path.exists(src_path):
        print("   利用可能なファイル:")
        for file in os.listdir(src_path):
            if file.endswith('.py'):
                print(f"     - {file}")
    
    sys.exit(1)


class MercariEbayTool:
    def __init__(self, config_path: str = "./config/config.yaml"):
        self.config_path = config_path
        self.config = None
        self.csv_reader = None
        self.model_extractor = None
        self.price_calculator = None
        self.browser_controller = None
        self.ebay_scraper = None
        self.output_handler = None
        self.logger = None
        
        self._initialize_components()

    def _initialize_components(self) -> None:
        """全コンポーネントを初期化"""
        try:
            # 設定読み込み
            self.config = ConfigLoader()
            self.config.load_all_configs()
            
            # ログ設定
            self._setup_logging()
            
            # 各コンポーネント初期化
            self.csv_reader = CSVReader(self.config)
            self.model_extractor = ModelExtractor(self.config)
            self.price_calculator = PriceCalculator(self.config)
            self.browser_controller = BrowserController(self.config)
            self.ebay_scraper = EbayScraper(self.config, self.browser_controller)
            self.output_handler = OutputHandler(self.config)
            
            self.logger.info("全コンポーネント初期化完了")
            
        except Exception as e:
            print(f"初期化エラー: {e}")
            sys.exit(1)

    def _setup_logging(self) -> None:
        """ログシステムを設定"""
        log_level = self.config.get_log_level()
        
        # ログディレクトリ作成
        os.makedirs("logs", exist_ok=True)
        
        # ログ設定
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/main.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)

    def run(self, input_file: str, **kwargs) -> str:
        """メイン処理を実行"""
        start_time = datetime.now()
        self.logger.info(f"処理開始: {input_file}")
        
        try:
            # 設定値上書き
            if kwargs:
                self.config.override_config(kwargs)
                self.logger.info(f"設定上書き: {kwargs}")
            
            # 設定サマリー表示
            config_summary = self.config.get_config_summary()
            self.logger.info(f"使用設定: {config_summary}")
            print(f"\n利益計算設定:")
            print(f"マークアップ率: {config_summary['markup_rate']:.1%}")
            print(f"固定利益: {config_summary['fixed_profit']:,}円")
            print(f"為替レート: {config_summary['exchange_rate']:.1f}円/USD")
            
            # 1. CSVファイル読み込み
            self.logger.info("CSVファイル読み込み開始")
            df = self.csv_reader.read_csv(input_file)
            original_data = self.csv_reader.get_processing_data(df)
            self.logger.info(f"読み込み完了: {len(original_data)}件")
            
            if not original_data:
                raise ValueError("処理対象のデータがありません")
            
            # 2. ブラウザ初期化
            self.logger.info("ブラウザ初期化")
            self.browser_controller.initialize_browser()
            
            # eBayセッション確認
            if not self.browser_controller.session_manager.check_ebay_session(self.browser_controller.driver):
                if not self.browser_controller.session_manager.wait_for_manual_login(self.browser_controller.driver):
                    raise SessionExpiredException("eBayログインに失敗しました")
            
            # 3. メイン処理ループ
            extraction_results = []
            search_results = []
            
            print(f"\n処理開始: {len(original_data)}件の商品を処理します...")
            
            with tqdm(total=len(original_data), desc="処理進捗") as pbar:
                for i, item in enumerate(original_data):
                    try:
                        pbar.set_description(f"処理中: {item['title'][:30]}...")
                        
                        # 型番抽出
                        extraction_result = self.model_extractor.extract_model(item['title'])
                        extraction_results.append(extraction_result)
                        
                        extracted_model = extraction_result.get('extracted_model', '')
                        
                        if extracted_model:
                            # eBay検索
                            search_result = self.ebay_scraper.search_model(extracted_model)
                            search_results.append(search_result)
                        else:
                            # 型番抽出失敗
                            search_results.append({
                                'search_query': item['title'],
                                'search_status': 'no_model',
                                'item_count': 0,
                                'best_item': None,
                                'error_message': '型番を抽出できませんでした'
                            })
                        
                        pbar.update(1)
                        
                        # チェックポイント保存（10件ごと）
                        if (i + 1) % 10 == 0:
                            self.logger.info(f"チェックポイント: {i + 1}/{len(original_data)}件完了")
                        
                    except RateLimitException as e:
                        self.logger.warning(f"レート制限検出: {e.wait_time}秒待機")
                        pbar.set_description(f"レート制限: {e.wait_time}秒待機中...")
                        import time
                        time.sleep(e.wait_time)
                        # リトライ
                        continue
                        
                    except Exception as e:
                        self.logger.error(f"処理エラー (アイテム {i}): {e}")
                        # エラー結果を追加
                        extraction_results.append({
                            'extracted_model': '',
                            'extraction_status': 'error',
                            'error_message': str(e)
                        })
                        search_results.append({
                            'search_query': item['title'],
                            'search_status': 'error',
                            'item_count': 0,
                            'best_item': None,
                            'error_message': str(e)
                        })
                        pbar.update(1)
                        continue
            
            # 4. 利益計算
            self.logger.info("利益計算開始")
            profit_items = []
            for i, item in enumerate(original_data):
                search_result = search_results[i] if i < len(search_results) else {}
                best_item = search_result.get('best_item')
                
                if best_item and best_item.get('price_usd', 0) > 0:
                    profit_items.append({
                        'index': i,
                        'mercari_price': item['price'],
                        'ebay_price_usd': best_item['price_usd']
                    })
                else:
                    profit_items.append({
                        'index': i,
                        'mercari_price': item['price'],
                        'ebay_price_usd': 0
                    })
            
            profit_results = self.price_calculator.batch_calculate_profits(profit_items)
            
            # 5. 結果出力
            self.logger.info("結果出力開始")
            result_data = self.output_handler.generate_result_data(
                original_data, extraction_results, search_results, profit_results
            )
            
            # CSVファイル出力
            output_file = self.output_handler.save_results_csv(input_file, result_data)
            
            # サマリーレポート生成
            summary = self.output_handler.generate_summary_report(result_data)
            summary_file = self.output_handler.save_summary_report(summary)
            
            # エラーログ出力
            error_log = self.output_handler.save_error_log(result_data)
            
            # 利益商品リスト出力
            profitable_file = self.output_handler.save_profitable_items(result_data)
            
            # コンソールにサマリー表示
            self.output_handler.print_summary_to_console(summary)
            
            # 処理時間計算
            end_time = datetime.now()
            processing_time = end_time - start_time
            
            print(f"\n処理完了!")
            print(f"処理時間: {processing_time}")
            print(f"結果ファイル: {output_file}")
            if profitable_file:
                print(f"利益商品リスト: {profitable_file}")
            if error_log:
                print(f"エラーログ: {error_log}")
            
            self.logger.info(f"処理完了: {processing_time}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"処理エラー: {e}")
            print(f"\nエラーが発生しました: {e}")
            return ""
            
        finally:
            # ブラウザ終了
            if self.browser_controller:
                self.browser_controller.close_browser()

    def dry_run(self, input_file: str, **kwargs) -> None:
        """ドライラン（実行シミュレーション）"""
        print("=== ドライランモード ===")
        
        try:
            # 設定値上書き
            if kwargs:
                self.config.override_config(kwargs)
            
            # 設定表示
            config_summary = self.config.get_config_summary()
            print(f"設定確認:")
            print(f"  マークアップ率: {config_summary['markup_rate']:.1%}")
            print(f"  固定利益: {config_summary['fixed_profit']:,}円")
            print(f"  為替レート: {config_summary['exchange_rate']:.1f}円/USD")
            
            # CSVファイル確認
            df = self.csv_reader.read_csv(input_file)
            original_data = self.csv_reader.get_processing_data(df)
            
            print(f"\nファイル確認:")
            print(f"  入力ファイル: {input_file}")
            print(f"  処理対象件数: {len(original_data)}件")
            
            # サンプルデータ表示
            if original_data:
                print(f"\nサンプルデータ（最初の3件）:")
                for i, item in enumerate(original_data[:3]):
                    print(f"  {i+1}. {item['title'][:50]}... ({item['price']:,}円)")
                    
                    # 型番抽出テスト
                    try:
                        extraction_result = self.model_extractor.extract_model(item['title'])
                        extracted_model = extraction_result.get('extracted_model', '')
                        if extracted_model:
                            print(f"     → 抽出型番: {extracted_model}")
                        else:
                            print(f"     → 型番抽出失敗")
                    except Exception as e:
                        print(f"     → 型番抽出エラー: {e}")
            
            print(f"\n予想処理時間: {len(original_data) * 7} 秒 ({len(original_data) * 7 / 60:.1f}分)")
            print("ドライラン完了")
            
        except Exception as e:
            print(f"ドライランエラー: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="メルカリ-eBay価格比較ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main.py --input mercari_data.csv
  python main.py --input data.csv --markup-rate 0.3 --fixed-profit 5000
  python main.py --input data.csv --dry-run
        """
    )
    
    # 必須引数
    parser.add_argument("--input", "-i", 
                       required=True,
                       help="入力CSVファイルパス")
    
    # オプション引数（設定上書き）
    parser.add_argument("--config", 
                       default="./config/config.yaml",
                       help="設定ファイルパス (default: ./config/config.yaml)")
    
    parser.add_argument("--markup-rate", 
                       type=float,
                       help="マークアップ率 (例: 0.2 = 20%%)")
    
    parser.add_argument("--fixed-profit", 
                       type=int,
                       help="固定利益額（円）")
    
    parser.add_argument("--exchange-rate", 
                       type=float,
                       help="為替レート（1USD = X円）")
    
    # 実行オプション
    parser.add_argument("--dry-run", 
                       action="store_true",
                       help="実行シミュレーション（実際の処理は行わない）")
    
    parser.add_argument("--headless", 
                       action="store_true",
                       help="ヘッドレスモードでブラウザを実行")
    
    args = parser.parse_args()
    
    # 入力ファイル存在確認
    if not os.path.exists(args.input):
        print(f"エラー: 入力ファイルが見つかりません: {args.input}")
        sys.exit(1)
    
    try:
        # ツール初期化
        tool = MercariEbayTool(args.config)
        
        # 設定上書き用の辞書作成
        overrides = {}
        if args.markup_rate is not None:
            overrides['markup_rate'] = args.markup_rate
        if args.fixed_profit is not None:
            overrides['fixed_profit'] = args.fixed_profit
        if args.exchange_rate is not None:
            overrides['exchange_rate'] = args.exchange_rate
        
        # 実行
        if args.dry_run:
            tool.dry_run(args.input, **overrides)
        else:
            output_file = tool.run(args.input, **overrides)
            if output_file:
                sys.exit(0)
            else:
                sys.exit(1)
                
    except ConfigurationError as e:
        print(f"設定エラー: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n処理が中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()