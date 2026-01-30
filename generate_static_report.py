import re
import requests
import argparse
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# ===============================
# 設定: 監視銘柄リスト
# ===============================
TARGET_TICKERS = [
    "285A.T", "9348.T", "7011.T", "8306.T", "6501.T", 
    "6701.T", "8593.T", "1969.T", "2749.T", "186A.T", 
    "4259.T", "3778.T", "5533.T"
]

# ===============================
# ロジック
# ===============================
def analyze_volume_zone(vol, max_vol):
    ratio = vol / max_vol if max_vol > 0 else 0
    labels = []
    if ratio >= 0.8:
        labels.append('<span style="color:#d32f2f; font-weight:bold;">★ 巨大なしこり</span>')
    elif ratio >= 0.5:
        labels.append('<span style="color:#f57f17; font-weight:bold;">厚いゾーン</span>')
    elif ratio <= 0.1:
        labels.append('<span style="color:#757575;">真空地帯</span>')
    return " / ".join(labels) if labels else ""

def get_margin_balance(ticker):
    url = f"https://finance.yahoo.co.jp/quote/{ticker}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        
        def get_val(label):
            # テキストノードを探してから、親のdtを取得する確実な方法
            target_text = soup.find(string=re.compile(label))
            if target_text and target_text.parent.name == "dt":
                dt = target_text.parent
                dd = dt.find_next_sibling("dd")
                if dd:
                    val_span = dd.find("span", class_=lambda c: c and "StyledNumber__value" in c)
                    if val_span:
                        return val_span.get_text(strip=True)
                    return dd.get_text(strip=True)
            return "-"

        # 日付取得
        date_span = soup.find("span", class_=lambda c: c and "MarginTransactionInformation__date" in c)
        date_str = date_span.get_text(strip=True) if date_span else ""
        date_str = date_str.replace("(", "").replace(")", "") # (01/23) -> 01/23

        return {
            "buy": get_val("信用買残"),
            "sell": get_val("信用売残"),
            "ratio": get_val("信用倍率"),
            "date": date_str
        }

    except Exception as e:
        print(f"Margin Error {ticker}: {e}")
        return {"buy": "-", "sell": "-", "ratio": "-", "date": ""}

def get_current_price(ticker):
    """yfinanceから最新の日足終値を取得"""
    try:
        # 直近2日間の日足データを取得（確実に終値を取るため）
        df = yf.download(ticker, period="2d", interval="1d", progress=False, threads=False)
        if df.empty:
            return None
        
        # マルチインデックスの場合、1階層目を取得
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 最新の終値を返す
        close_price = df["Close"].iloc[-1]
        return float(close_price)
        
    except Exception as e:
        print(f"Price Error {ticker}: {e}")
        return None

def calc_profile(ticker, mode="short"):
    period = "5d" if mode == "short" else "1mo"
    interval = "1m" if mode == "short" else "1d"
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, threads=False)
        if df.empty: return []
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        price = df["Close"]
        volume = df["Volume"]
        current = price.iloc[-1]
        
        bins = np.linspace(price.min(), price.max(), 31) # 30区間
        indices = np.digitize(price, bins) - 1
        
        profile = {}
        for i, vol in zip(indices, volume):
            if 0 <= i < len(bins)-1:
                p_key = int((bins[i] + bins[i+1])/2)
                profile[p_key] = profile.get(p_key, 0) + vol
                
        sorted_profile = sorted(profile.items(), key=lambda x: x[0], reverse=True)
        return sorted_profile, current
    except:
        return [], 0

def generate_table_html(profile, current_price, title):
    if not profile: return f"<p>{title}: データなし</p>"
    
    max_vol = max(p[1] for p in profile)
    total_vol = sum(p[1] for p in profile)
    bin_width = abs(profile[0][0] - profile[1][0]) if len(profile) > 1 else 0
    
    rows = []
    limit = 0
    for p, v in profile:
        if total_vol > 0 and (v/total_vol) < 0.01: continue
        limit += 1
        if limit > 15: break
        
        lower = int(p - bin_width/2)
        upper = int(p + bin_width/2)
        
        # 現在値の強調
        row_style = ""
        eval_text = analyze_volume_zone(v, max_vol)
        
        if lower <= current_price < upper:
            row_style = "background-color: #e3f2fd;" # 現在値付近を青く
            eval_text += ' <span style="font-weight:bold; color:#1565c0;">📍 現在値</span>'

        rows.append(f"""
        <tr style="{row_style}">
            <td style="padding:6px; border:1px solid #eee; text-align:center; font-size:13px;">{lower:,} - {upper:,}</td>
            <td style="padding:6px; border:1px solid #eee; text-align:right; font-size:13px;">{v:,}</td>
            <td style="padding:6px; border:1px solid #eee; font-size:12px;">{eval_text}</td>
        </tr>
        """)
        
    return f"""
    <div style="margin-bottom: 16px;">
        <h4 style="margin: 8px 0 4px 0; font-size:14px; color:#555;">{title}</h4>
        <table style="width:100%; border-collapse:collapse;">
            <thead style="background-color:#f8fafc;">
                <tr>
                    <th style="padding:6px; border:1px solid #ddd; font-size:12px;">価格帯</th>
                    <th style="padding:6px; border:1px solid #ddd; font-size:12px;">出来高</th>
                    <th style="padding:6px; border:1px solid #ddd; font-size:12px;">評価</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """

def process_ticker(code):
    html_parts = []
    
    # データ取得
    try:
        ticker = f"{code}" if ".T" in code else f"{code}.T"
        
        # 正確な終値を取得
        current_price = get_current_price(ticker)
        
        # 株価情報（銘柄名用）
        ticker_info = yf.Ticker(ticker)
        try:
            name = ticker_info.info.get("shortName", code)
        except:
            name = code
            
        margin = get_margin_balance(ticker)
        vp_short, cur_short = calc_profile(ticker, "short")
        vp_mid, cur_mid = calc_profile(ticker, "mid")
        
        # 終値が取得できなかった場合はyfinanceのデータをフォールバック
        if current_price is None:
            current_price = cur_short if cur_short > 0 else cur_mid
            if current_price == 0:
                current_price = 0  # データなし
        
        # 各銘柄のブロックHTML
        price_display = f"{int(current_price):,}円" if current_price > 0 else "データなし"
        
        html_parts.append(f"""
        <div class="ticker-card" style="border: 2px solid #333; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
            <h2 style="margin-top:0; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                {code} <span style="font-size:0.8em; color:#666;">{name}</span>
                <span style="float:right; font-size:0.6em; font-weight:normal; margin-top:8px;">現在値: {price_display}</span>
            </h2>
            
            <div style="background:#f1f8e9; padding:8px; border-radius:4px; font-size:13px; margin-bottom:12px;">
                <strong>信用需給 ({margin['date']})</strong>: 
                <span style="color:#d32f2f;">買残 {margin['buy']}</span> / 
                <span style="color:#1976d2;">売残 {margin['sell']}</span> / 
                倍率 {margin['ratio']}倍
            </div>
            
            <div style="display:flex; flex-wrap:wrap; gap:16px;">
                <div style="flex:1; min-width:300px;">
                    {generate_table_html(vp_short, current_price, "⚡️ 短期 (1週/1分足)")}
                </div>
                <div style="flex:1; min-width:300px;">
                    {generate_table_html(vp_mid, current_price, "📅 中期 (1ヶ月/日足)")}
                </div>
            </div>
        </div>
        """)
        
    except Exception as e:
        html_parts.append(f'<div style="color:red">Error processing {code}: {e}</div>')
        
    return "".join(html_parts)

# ===============================
# メイン処理
# ===============================
def main():
    # JST (UTC+9) に変換
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    
    # ヘッダー
    full_html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>需給レポート一覧</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; padding: 10px; max-width: 900px; margin: 0 auto; background-color: #fcfcfc; }}
            h1 {{ text-align: center; color: #333; }}
            .nav {{ text-align: center; margin-bottom: 20px; }}
            .nav a {{ margin: 0 5px; color: #2196F3; text-decoration: none; font-size: 14px; }}
            @media (max-width: 600px) {{
                .ticker-card {{ padding: 8px !important; }}
                h2 {{ font-size: 1.2em; }}
            }}
        </style>
    </head>
    <body>
        <h1>📊 株需給レポート一括確認</h1>
        <p style="text-align:center; color:#666; font-size:12px;">更新: {now_str}</p>
        
        <div class="nav">
            {' '.join([f'<a href="#{t}">{t}</a>' for t in TARGET_TICKERS])}
        </div>
    """
    
    # 各銘柄の処理
    for code in TARGET_TICKERS:
        print(f"Processing {code}...")
        full_html += f'<div id="{code}">'
        full_html += process_ticker(code)
        full_html += '</div>'
        
    # フッター
    full_html += """
    </body>
    </html>
    """
    
    filename = "index.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    print(f"Successfully generated {filename} with check for {len(TARGET_TICKERS)} tickers.")

if __name__ == "__main__":
    main()
