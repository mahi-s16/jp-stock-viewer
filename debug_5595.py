import requests
from bs4 import BeautifulSoup
import re
import yfinance as yf

def get_current_price(ticker):
    code = str(ticker).replace(".T", "").strip()
    url = f"https://finance.yahoo.co.jp/quote/{code}"
    print(f"URL: {url}")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        
        price_tag = soup.select_one('span[class*="PriceBoard__price__"]')
        if not price_tag:
            price_tag = soup.select_one('span[class*="StyledNumber__value__"], span[class*="_3rXWJKZF"]')
        
        if price_tag:
            val = price_tag.get_text()
            print(f"Scraped value: '{val}'")
            price_text = val.replace(",", "")
            try:
                return float(price_text)
            except ValueError:
                print(f"Could not convert '{price_text}' to float")
                return None
        else:
            print("No price tag found")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

ticker = "5595.T"
price = get_current_price(ticker)
print(f"Result for {ticker}: {price}")

print("Testing yfinance...")
df = yf.download(ticker, period="5d", interval="1d")
print(df)
