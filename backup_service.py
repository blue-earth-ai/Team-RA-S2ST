import os
import logging
from ftplib import FTP_TLS
import threading
from dotenv import load_dotenv  # ★追加

# ★追加: ここで .env を読み込む
load_dotenv()

# 設定読み込み
FTP_HOST = os.environ.get('FTP_HOST')
FTP_USER = os.environ.get('FTP_USER')
FTP_PASS = os.environ.get('FTP_PASS')
FTP_PATH = os.environ.get('FTP_PATH', '/')
FTP_AUDIO_PATH = os.environ.get('FTP_PATH', '/') + '/audio_cache'

logger = logging.getLogger(__name__)

def get_ftp_connection():
    """FTP接続（FTPS）を確立する"""
    # 念のため関数内でも再確認（デバッグ用）
    if not all([FTP_HOST, FTP_USER, FTP_PASS]):
        # ここでデバッグログを出すと分かりやすい
        logger.warning(f"FTP設定不足: HOST={FTP_HOST}, USER={FTP_USER}, PASS={'OK' if FTP_PASS else 'NG'}")
        return None
    
    try:
        ftps = FTP_TLS(FTP_HOST)
        ftps.login(FTP_USER, FTP_PASS)
        ftps.prot_p() # データ通信を暗号化
        
        # ディレクトリ移動（なければ作る）
        if FTP_PATH != '/':
            try:
                ftps.cwd(FTP_PATH)
            except:
                try:
                    ftps.mkd(FTP_PATH)
                    ftps.cwd(FTP_PATH)
                except Exception as e:
                    logger.error(f"FTPディレクトリ移動失敗: {e}")
                    return None
        return ftps
    except Exception as e:
        logger.error(f"FTP接続エラー: {e}")
        return None

def download_db(local_path, remote_filename):
    """起動時に実行: さくらからDBをダウンロード"""
    ftps = get_ftp_connection()
    if not ftps: return False

    try:
        # ファイルが存在するか確認
        files = ftps.nlst()
        if remote_filename in files:
            with open(local_path, 'wb') as f:
                ftps.retrbinary(f'RETR {remote_filename}', f.write)
            logger.info(f"★バックアップ復元成功: {remote_filename}")
            ftps.quit()
            return True
        else:
            logger.info(f"バックアップファイルが見つかりません（初回起動）: {remote_filename}")
            ftps.quit()
            return False
    except Exception as e:
        logger.error(f"ダウンロード失敗: {e}")
        return False

def upload_db_worker(local_path, remote_filename):
    """バックグラウンドで実行されるアップロード処理"""
    ftps = get_ftp_connection()
    if not ftps: return

    try:
        with open(local_path, 'rb') as f:
            ftps.storbinary(f'STOR {remote_filename}', f)
        logger.info(f"★バックアップ保存完了: {remote_filename}")
        ftps.quit()
    except Exception as e:
        logger.error(f"アップロード失敗: {e}")

def upload_db_background(local_path, remote_filename):
    """メイン処理を止めないように別スレッドでアップロード"""
    if not os.path.exists(local_path):
        return
    thread = threading.Thread(target=upload_db_worker, args=(local_path, remote_filename), daemon=True)
    thread.start()

def upload_audio_worker(local_filepath, remote_filename):
    """バックグラウンドで実行される音声ファイルアップロード処理"""
    if not all([FTP_HOST, FTP_USER, FTP_PASS]): return

    ftps = None
    try:
        ftps = FTP_TLS(FTP_HOST)
        ftps.login(FTP_USER, FTP_PASS)
        ftps.prot_p()
        
        # 音声専用フォルダに移動（なければ作成）
        try:
            ftps.cwd(FTP_AUDIO_PATH)
        except:
            try:
                ftps.mkd(FTP_AUDIO_PATH)
                ftps.cwd(FTP_AUDIO_PATH)
            except Exception as e:
                logger.error(f"FTPオーディオディレクトリ作成・移動失敗: {e}")
                return

        with open(local_filepath, 'rb') as f:
            ftps.storbinary(f'STOR {remote_filename}', f)
        logger.info(f"★音声キャッシュ保存完了: {remote_filename} to {FTP_AUDIO_PATH}")
        ftps.quit()
    except Exception as e:
        logger.error(f"音声キャッシュアップロード失敗: {e}")
    finally:
        if ftps:
            try: ftps.quit()
            except: pass

def upload_audio_background(local_filepath, remote_filename):
    thread = threading.Thread(target=upload_audio_worker, args=(local_filepath, remote_filename), daemon=True)
    thread.start()

def restore_audio_cache():
    """Render起動時にさくらサーバーから音声ファイルをダウンロード"""
    ftps = get_ftp_connection()
    if not ftps: return

    try:
        # 音声フォルダに移動（存在しない場合はスキップ）
        try:
            ftps.cwd(FTP_AUDIO_PATH)
        except:
            logger.info("音声キャッシュフォルダがまだありません（スキップします）")
            ftps.quit()
            return

        static_audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'audio')
        os.makedirs(static_audio_dir, exist_ok=True)

        files = ftps.nlst()
        restored_count = 0
        for filename in files:
            # .mp3だけ対象にする
            if filename.endswith('.mp3'):
                local_filepath = os.path.join(static_audio_dir, filename)
                # 既にローカルにある場合はスキップ（時間短縮）
                if not os.path.exists(local_filepath):
                    with open(local_filepath, 'wb') as f:
                        ftps.retrbinary(f'RETR {filename}', f.write)
                    restored_count += 1
                
        logger.info(f"Render起動時、音声キャッシュを {restored_count} 件復元しました。")
        ftps.quit()
    except Exception as e:
        logger.warning(f"音声キャッシュ復元中にエラーが発生しました: {e}")