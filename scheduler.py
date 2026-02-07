import time
import subprocess
from datetime import datetime, timedelta, timezone

def is_market_hours():
    """現在時刻が平日の 9:00 - 15:30 (JST) かどうかを判定"""
    # 日本時間 (JST = UTC+9) の生成
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    
    # 平日判定 (0=月, 4=金, 5=土, 6=日)
    if now.weekday() >= 5:
        return False
    
    # 時間判定
    start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return start_time <= now <= end_time

def run_update():
    """レポート生成プログラムを実行"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新を開始します...")
    try:
        # generate_static_report.py を実行
        result = subprocess.run(["python3", "generate_static_report.py"], capture_output=True, text=True)
        if result.returncode == 0:
            print("更新が正常に完了しました。")
        else:
            print(f"更新中にエラーが発生しました:\n{result.stderr}")
    except Exception as e:
        print(f"実行中に例外が発生しました: {e}")

def main():
    print("株需給レポート定期更新スケジューラーを起動しました。")
    print("条件: 平日 9:00 - 15:30 (JST) の間、10分おきに実行")
    
    while True:
        if is_market_hours():
            run_update()
            print("次の更新まで10分待機します...")
            time.sleep(600)  # 10分 (600秒)
        else:
            # 市場時間外の場合は5分おきにチェック
            now_jst = datetime.now(timezone(timedelta(hours=9)))
            print(f"[{now_jst.strftime('%H:%M:%S')}] 現在は市場時間外です。5分後に再確認します。")
            time.sleep(300)  # 5分 (300秒)

if __name__ == "__main__":
    main()
