import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd

def get_yfinance_price(ticker):
    print(f"Fetching {ticker} from yfinance (1m)...")
    df = yf.download(ticker, period="1d", interval="1m", progress=False)
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df["Close"].iloc[-1], df.index[-1]
    
    print(f"Fetching {ticker} from yfinance (1d fallback)...")
    df = yf.download(ticker, period="5d", interval="1d", progress=False)
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df["Close"].iloc[-1], df.index[-1]
    return None, None

def get_scraped_price(ticker):
    code = ticker.replace(".T", "")
    url = f"https://finance.yahoo.co.jp/quote/{code}"
    print(f"Scraping {url}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.content, "html.parser")
    
    # 典型的な現在値のセレクタ (Yahoo JP)
    # _3rXWJKZF _11S67P_p は時期によって変わる可能性があるが、現在のものを探す
    # 通常、<span> か <strong> に入っている
    price_element = soup.find("span", class_="_3rXWJKZF") # これはよく変わる
    if not price_element:
        # 他の候補
        price_element = soup.select_one('span[data-test="price"]')
    
    if not price_element:
        # さらに汎用的な探し方: metaタグやtitleから
        title = soup.find("title").text
        # 例: "三菱ＵＦＪフィナンシャル・グループ【8306】：株価・株式情報 - Yahoo!ファイナンス"
        # 価格はタイトルの最初の方にある場合があるが、JP版は違う。
        # 本文中の大きな数字を探す
        for span in soup.find_all("span"):
            text = span.get_text().replace(",", "")
            if text.replace(".", "").isdigit() and len(text) > 2:
                # 非常に乱暴な探し方だが、デバッグ用
                print(f"Found potential price in span: {text}")
                
    if price_element:
        return price_element.get_text()
    return "Not found"

tickers = ["8306.T", "9348.T", "285A.T"]
for t in tickers:
    yf_p, yf_t = get_yfinance_price(t)
    sc_p = get_scraped_price(t)
    print(f"[{t}] yfinance: {yf_p} (at {yf_t}), Scraped: {sc_p}")
