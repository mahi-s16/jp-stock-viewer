import re
import requests
import argparse
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ===============================
# ロジック（app.pyから流用）
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
        text = r.text
        # 簡易スクレイピング
        m_buy = re.search(r"信用買残([\d,]+)株", text)
        m_sell = re.search(r"信用売残([\d,]+)株", text)
        m_ratio = re.search(r"信用倍率([\d,.]+)倍", text)
        return {
            "buy": m_buy.group(1) if m_buy else "-",
            "sell": m_sell.group(1) if m_sell else "-",
            "ratio": m_ratio.group(1) if m_ratio else "-"
        }
    except:
        return {"buy": "-", "sell": "-", "ratio": "-"}

def calc_profile(ticker, mode="short"):
    period = "5d" if mode == "short" else "1mo"
    interval = "1m" if mode == "short" else "1d"
    
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty: return []
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        price = df["Close"]
        volume = df["Volume"]
        bins = np.linspace(price.min(), price.max(), 31)
        indices = np.digitize(price, bins) - 1
        
        profile = {}
        for i, vol in zip(indices, volume):
            if 0 <= i < len(bins)-1:
                p_key = int((bins[i] + bins[i+1])/2)
                profile[p_key] = profile.get(p_key, 0) + vol
                
        return sorted(profile.items(), key=lambda x: x[0], reverse=True)
    except:
        return []

def generate_table_html(profile, title):
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
        eval_text = analyze_volume_zone(v, max_vol)
        
        rows.append(f"""
        <tr>
            <td style="padding:8px; border:1px solid #ddd; text-align:center;">{lower:,} - {upper:,}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{v:,}</td>
            <td style="padding:8px; border:1px solid #ddd;">{eval_text}</td>
        </tr>
        """)
        
    return f"""
    <div style="margin-bottom: 24px;">
        <h3 style="border-left: 4px solid #2196F3; padding-left: 8px; margin-bottom: 8px;">{title}</h3>
        <table style="width:100%; border-collapse:collapse; font-size:14px;">
            <thead style="background-color:#f5f5f5;">
                <tr>
                    <th style="padding:8px; border:1px solid #ccc;">価格帯 (円)</th>
                    <th style="padding:8px; border:1px solid #ccc;">出来高 (株)</th>
                    <th style="padding:8px; border:1px solid #ccc;">評価</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """

# ===============================
# メイン処理
# ===============================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code", default="7203", nargs="?", help="Ticker Code (e.g. 7203)")
    args = parser.parse_args()
    
    ticker = f"{args.code}.T" if not args.code.endswith(".T") and args.code.isdigit() else args.code
    margin = get_margin_balance(ticker)
    vp_short = calc_profile(ticker, "short")
    vp_mid = calc_profile(ticker, "mid")
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{args.code} 需給レポート</title>
        <style>body {{ font-family: sans-serif; padding: 16px; max-width: 800px; margin: 0 auto; line-height: 1.6; }}</style>
    </head>
    <body>
        <h1>📊 {args.code} 需給レポート</h1>
        <p style="color:#666; font-size:12px; text-align:right;">作成日時: {now_str}</p>
        
        <div style="background:#f8f9fa; padding:12px; border-radius:4px; border:1px solid #ddd; margin-bottom:20px;">
            <strong>信用情報</strong><br>
            買残: {margin['buy']}株 / 売残: {margin['sell']}株 / 倍率: {margin['ratio']}倍
        </div>
        
        {generate_table_html(vp_short, "直近1週間 (短期・1分足ベース)")}
        {generate_table_html(vp_mid, "直近1ヶ月 (中期・日足ベース)")}
        
    </body>
    </html>
    """
    
    filename = "index.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    main()
