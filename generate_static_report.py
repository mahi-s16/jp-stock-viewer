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
    "3778.T", "5572.T", "8035.T", "6857.T",
    "6146.T", "6920.T", "9101.T", "9104.T", "9432.T",
    "9984.T", "7203.T", "8058.T"
]

def normalize_ticker(code):
    """ティッカーを.T形式に統一"""
    code = str(code).strip()
    if not code: return ""
    if code.endswith(".T"): return code
    if re.match(r'^\d{4}[A-Z]?$', code): # 285A or 7203
        return f"{code}.T"
    return code

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
    ticker = normalize_ticker(ticker)
    try:
        # 確実に終値を取るため、期間を少し長めに取る
        df = yf.download(ticker, period="5d", interval="1d", progress=False, threads=False)
        if df.empty:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 欠損値を除去して最新の終値を取得
        valid_closes = df["Close"].dropna()
        if valid_closes.empty:
            return None
        return float(valid_closes.iloc[-1])
        
    except Exception as e:
        print(f"Price Error {ticker}: {e}")
        return None

def get_heat_score(ticker):
    """出来高の急増度（ヒートスコア）を算出"""
    ticker = normalize_ticker(ticker)
    try:
        # 5分足(5d分)と日足(5d分)をまとめて取得を検討したいが、インターバルが違うので個別
        df_5m = yf.download(ticker, period="5d", interval="5m", progress=False, threads=False)
        if df_5m.empty or len(df_5m) < 5:
            return 0.0, 0.0, 0.0
            
        if isinstance(df_5m.columns, pd.MultiIndex):
            df_5m.columns = df_5m.columns.get_level_values(0)
            
        avg_vol = df_5m["Volume"].mean()
        current_vol = df_5m["Volume"].iloc[-1]
        score = current_vol / avg_vol if avg_vol > 0 else 0
        
        # 前日比計算用
        df_1d = yf.download(ticker, period="5d", interval="1d", progress=False, threads=False)
        change_pct = 0.0
        if not df_1d.empty and len(df_1d) >= 2:
            if isinstance(df_1d.columns, pd.MultiIndex):
                df_1d.columns = df_1d.columns.get_level_values(0)
            
            closes = df_1d["Close"].dropna()
            if len(closes) >= 2:
                current_close = closes.iloc[-1]
                prev_close = closes.iloc[-2]
                if prev_close > 0:
                    change_pct = ((current_close - prev_close) / prev_close) * 100
            
        return round(score, 2), current_vol, round(change_pct, 2)
        
    except Exception as e:
        print(f"Heat score error {ticker}: {e}")
        return 0.0, 0.0, 0.0

def get_heat_color(score):
    """スコアに応じたヒートマップの色を返す"""
    if score >= 3.0:
        return "#ff5252", "#fff" # 鮮やかな赤
    elif score >= 2.0:
        return "#ff9800", "#fff" # オレンジ
    elif score >= 1.5:
        return "#ffd740", "#333" # 黄色
    elif score >= 1.0:
        return "#e0e0e0", "#666" # グレー（標準）
    elif score > 0:
        return "#c8e6c9", "#388e3c" # 薄い緑（低調）
    return "#f5f5f5", "#ccc" # データなし

def get_rsi(ticker, period="14d"):
    """RSI(14)を算出"""
    try:
        # 過去1ヶ月分程度の日足データを取得
        df = yf.download(ticker, period="1mo", interval="1d", progress=False, threads=False)
        if df.empty or len(df) < 15:
            return 50.0 # デフォルト
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi.iloc[-1], 1)
    except Exception as e:
        print(f"RSI error {ticker}: {e}")
        return 50.0

def get_wall_info(current_price, vp_data):
    """最寄りの壁（しこり・真空）への距離を算出"""
    try:
        if not vp_data or current_price is None or current_price <= 0:
            return "N/A", 0
            
        max_vol = max(v[1] for v in vp_data)
        
        # 上方向の壁を探す
        # vp_dataは価格降順なので、下から上に見ていく
        target_wall = None
        for p, v in reversed(vp_data):
            if p > current_price:
                ratio = v / max_vol if max_vol > 0 else 0
                if ratio >= 0.8: # 巨大なしこりレベル
                    target_wall = (p, "しこり")
                    break
                elif ratio <= 0.1: # 真空地帯レベル
                    target_wall = (p, "真空")
                    break
            
        if target_wall:
            p, wall_name = target_wall
            dist_pct = ((p - current_price) / current_price) * 100
            return wall_name, round(dist_pct, 1)
            
        return "真空", 5.0 # 上に明確な壁がない
    except Exception as e:
        return "Error", 0

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
        
        # 日本語の銘柄名を取得
        name = get_japanese_name(ticker)
        if not name:
            try:
                ticker_info = yf.Ticker(ticker)
                name = ticker_info.info.get("shortName", code)
            except:
                name = code
            
        margin = get_margin_balance(ticker)
        vp_short, cur_short = calc_profile(ticker, "short")
        vp_mid, cur_mid = calc_profile(ticker, "mid")
        
        # ヒートスコア・騰落率取得
        heat_score, last_vol, change_pct = get_heat_score(ticker)
        
        # RSI取得
        rsi_val = get_rsi(ticker)
        
        # 壁への距離取得 (中期の壁を基準にする)
        wall_name, wall_dist = get_wall_info(current_price, vp_mid)
        
        # 終値が取得できなかった場合はyfinanceのデータをフォールバック
        if current_price is None or current_price == 0:
            current_price = cur_short if (cur_short and cur_short > 0) else (cur_mid if (cur_mid and cur_mid > 0) else 0)
        
        # 数値化を保証
        current_price = float(current_price) if current_price else 0.0

        # スパイク判定バッジ
        spike_badge = ""
        if heat_score >= 3.0:
            spike_badge = '<span style="background:#ff5252; color:white; padding:2px 8px; border-radius:12px; font-size:0.5em; vertical-align:middle; margin-left:8px;">🔥 出来高急騰!</span>'
        elif heat_score >= 1.5:
            spike_badge = '<span style="background:#ff9800; color:white; padding:2px 8px; border-radius:12px; font-size:0.5em; vertical-align:middle; margin-left:8px;">⚡️ 活性化</span>'

        # 各銘柄のブロックHTML
        price_display = f"{int(current_price):,}円" if current_price > 0 else "データなし"
        
        html_parts.append(f"""
        <div class="ticker-card" style="border: 2px solid #333; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
            <h2 style="margin-top:0; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                {code} <span style="font-size:0.8em; color:#666;">{name}</span>
                {spike_badge}
                <span style="float:right; font-size:0.6em; font-weight:normal; margin-top:8px;">現在値: {price_display}</span>
            </h2>
            
            <div style="background:#f1f8e9; padding:8px; border-radius:4px; font-size:13px; margin-bottom:12px;">
                <strong>信用需給 ({margin['date']})</strong>: 
                <span style="color:#d32f2f;">買残 {margin['buy']}</span> / 
                <span style="color:#1976d2;">売残 {margin['sell']}</span> / 
                倍率 {margin['ratio']}倍 | 
                <strong>勢い</strong>: <span style="font-weight:bold; color:{'#d32f2f' if heat_score >= 2 else '#333'};">{heat_score}倍</span> (直近5分出来高/平均)
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
        
        return "".join(html_parts), heat_score, name, current_price, rsi_val, wall_name, wall_dist, change_pct
        
    except Exception as e:
        return f'<div style="color:red">Error processing {code}: {e}</div>', 0, code, 0, 50, "Error", 0, 0

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
        
        <!-- ヒートマップセクション -->
        <div id="heatmap-container" style="margin-bottom:24px;">
            <h3 style="margin-top:0; color:#333;">🌡️ 13銘柄ヒートマップ (勢い)</h3>
            <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap:8px;">
                <!-- ヒートマップタイルがここに挿入される -->
            </div>
        </div>

        <!-- ランキングセクション -->
        <div id="heat-ranking" style="background:#fff; border:2px solid #ff5252; border-radius:8px; padding:16px; margin-bottom:24px;">
            <h3 style="margin-top:0; color:#ff5252;">🔥 資金流入スピード・ランキング (直近5分)</h3>
            <table style="width:100%; border-collapse:collapse; font-size:14px;">
                <thead style="background:#fee2e2;">
                    <tr>
                        <th style="padding:8px; border-bottom:2px solid #ff5252;">順位</th>
                        <th style="padding:8px; border-bottom:2px solid #ff5252;">銘柄</th>
                        <th style="padding:8px; border-bottom:2px solid #ff5252;">勢いスコア</th>
                        <th style="padding:8px; border-bottom:2px solid #ff5252;">現在値</th>
                    </tr>
                </thead>
                <tbody id="ranking-body">
                    <!-- JSまたはPythonで挿入 -->
                </tbody>
            </table>
        </div>

        <div class="nav">
            {' '.join([f'<a href="#{t}">{t}</a>' for t in TARGET_TICKERS])}
        </div>
    """
    
    # 各銘柄の処理
    ticker_results = []
    for code in TARGET_TICKERS:
        print(f"Processing {code}...")
        html, score, name, price, rsi, wall_name, wall_dist, change_pct = process_ticker(code)
        ticker_results.append({
            "code": code,
            "html": html,
            "score": score,
            "name": name,
            "price": price,
            "rsi": rsi,
            "wall_name": wall_name,
            "wall_dist": wall_dist,
            "change_pct": change_pct
        })
    
    # スコアでソート
    ranking = sorted(ticker_results, key=lambda x: x["score"], reverse=True)
    
    # ランキング行の生成
    ranking_rows = []
    for i, res in enumerate(ranking[:10]):
        heat_style = "font-weight:bold; color:#ff5252;" if res["score"] >= 2 else ""
        
        # 前日比の色付け
        change_color = "#d32f2f" if res["change_pct"] > 0 else ("#388e3c" if res["change_pct"] < 0 else "#666")
        change_sign = "+" if res["change_pct"] > 0 else ""
        
        # ステータスバッジの生成 (ランキング用)
        badge = ""
        if res["score"] >= 3.0:
            badge = '<span style="background:#ff5252; color:white; padding:1px 6px; border-radius:10px; font-size:0.7em; margin-left:4px; white-space:nowrap;">🔥 急騰</span>'
        elif res["score"] >= 1.5:
            badge = '<span style="background:#ff9800; color:white; padding:1px 6px; border-radius:10px; font-size:0.7em; margin-left:4px; white-space:nowrap;">⚡️ 活性</span>'
        
        ranking_rows.append(f"""
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee; text-align:center;">{i+1}</td>
            <td style="padding:8px; border-bottom:1px solid #eee;">
                <a href="#{res['code']}" style="font-weight:bold; text-decoration:none; color:#1565c0;">{res['code']}</a> {badge}<br>
                <span style="font-size:0.8em; color:#666;">{res['name']}</span>
            </td>
            <td style="padding:8px; border-bottom:1px solid #eee; text-align:center; {heat_style}">{res['score']}倍</td>
            <td style="padding:8px; border-bottom:1px solid #eee; text-align:right;">
                <span style="font-weight:bold;">{int(res['price']):,}円</span><br>
                <span style="font-size:0.85em; color:{change_color};">{change_sign}{res['change_pct']}%</span>
            </td>
        </tr>
        """)
    
    full_html = full_html.replace('<!-- JSまたはPythonで挿入 -->', "".join(ranking_rows))

    # ヒートマップタイルの生成
    heatmap_tiles = []
    for res in ticker_results:
        bg_color, text_color = get_heat_color(res["score"])
        
        # RSIの色付け
        rsi_style = ""
        if res["rsi"] >= 70: rsi_style = "color:#d32f2f; font-weight:bold;"
        elif res["rsi"] <= 30: rsi_style = "color:#388e3c; font-weight:bold;"
        
        heatmap_tiles.append(f"""
        <a href="#{res['code']}" style="text-decoration:none; color:inherit;">
            <div style="background:{bg_color}; color:{text_color}; padding:10px; border-radius:8px; text-align:center; box-shadow:0 2px 4px rgba(0,0,0,0.1); transition:transform 0.2s; min-height:100px; display:flex; flex-direction:column; justify-content:space-between;" 
                 onmouseover="this.style.transform='scale(1.03)'" onmouseout="this.style.transform='scale(1)'">
                <div style="font-weight:bold; font-size:13px; border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:4px; margin-bottom:4px;">{res['code']}</div>
                
                <div style="display:grid; grid-template-columns: 1fr; gap:2px; font-size:11px;">
                    <div title="バースト・スコア">💥 <span style="font-weight:bold; font-size:14px;">{res['score']}</span>x</div>
                    <div title="壁までの距離" style="white-space:nowrap;">🚧 {res['wall_name']} <span style="font-weight:bold;">{res['wall_dist']}</span>%</div>
                    <div title="RSI(14)">📊 RSI <span style="{rsi_style}">{res['rsi']}</span></div>
                </div>
                
                <div style="font-size:9px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; opacity:0.8; margin-top:6px;">{res['name']}</div>
            </div>
        </a>
        """)
    
    full_html = full_html.replace('<!-- ヒートマップタイルがここに挿入される -->', "".join(heatmap_tiles))

    for res in ticker_results:
        full_html += f'<div id="{res["code"]}">'
        full_html += res["html"]
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
