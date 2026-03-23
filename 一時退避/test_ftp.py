import os
from dotenv import load_dotenv
from ftplib import FTP_TLS

# .envファイルを読み込む
print("--- 1. 設定ファイルの読み込みテスト ---")
load_success = load_dotenv()
if load_success:
    print("✅ .env ファイルを検出しました。")
else:
    print("❌ .env ファイルが見つかりません。")
    print("   (このスクリプトと同じ場所に .env ファイルがあるか確認してください)")

# 環境変数の取得
ftp_host = os.environ.get('FTP_HOST')
ftp_user = os.environ.get('FTP_USER')
ftp_pass = os.environ.get('FTP_PASS')
ftp_path = os.environ.get('FTP_PATH')

# 読み込み結果の表示（パスワードは隠す）
print(f"HOST: {ftp_host}")
print(f"USER: {ftp_user}")
print(f"PASS: {'******' if ftp_pass else 'None (未設定)'}")
print(f"PATH: {ftp_path}")

if not all([ftp_host, ftp_user, ftp_pass]):
    print("\n❌ エラー: 必要な設定が足りていません。接続テストを中止します。")
    exit()

print("\n--- 2. 接続テスト開始 ---")
try:
    # 1. 接続
    print(f"Connecting to {ftp_host}...")
    ftps = FTP_TLS(ftp_host)
    
    # 2. ログイン
    print("Logging in...")
    ftps.login(ftp_user, ftp_pass)
    
    # 3. 暗号化通信の開始
    ftps.prot_p()
    print("✅ ログイン成功 (暗号化通信確立)")
    
    # 4. フォルダ移動テスト
    if ftp_path and ftp_path != '/':
        print(f"Changing directory to {ftp_path}...")
        try:
            ftps.cwd(ftp_path)
            print("✅ フォルダ移動成功")
        except Exception as e:
            print(f"⚠️ フォルダ移動失敗 (フォルダがない可能性があります): {e}")
            print("   フォルダ作成を試みます...")
            try:
                ftps.mkd(ftp_path)
                ftps.cwd(ftp_path)
                print("✅ フォルダ作成＆移動成功")
            except Exception as mkd_e:
                print(f"❌ フォルダ作成失敗: {mkd_e}")

    # 5. ファイル一覧取得
    print("Listing files...")
    files = ftps.nlst()
    print(f"ファイル一覧: {files}")
    
    ftps.quit()
    print("\n🎉 テスト完了: FTP接続は正常です！")

except Exception as e:
    print(f"\n❌ 接続エラーが発生しました:\n{e}")
    print("\n【考えられる原因】")
    print("1. ホスト名、ユーザー名、パスワードの間違い")
    print("2. さくらインターネットの「国外IPアドレスフィルタ」がONになっている（Render等の場合）")
    print("3. 社内ネットワーク等のファイアウォールでFTP(21番ポート)が閉じられている")