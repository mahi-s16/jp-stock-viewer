import requests
from bs4 import BeautifulSoup
import re

def check_jsf_data(ticker):
    url = f"https://finance.yahoo.co.jp/quote/{ticker}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 貸借取引情報 (JSF) を探す
        jsf_section = soup.find(string=re.compile("貸借取引情報"))
        if jsf_section:
            print(f"[{ticker}] JSF section found!")
            # 日付を探す
            # JSFの日付は別のクラス名かもしれない
            # とりあえず周辺のテキストを出す
            return True
        else:
            print(f"[{ticker}] JSF section NOT found.")
            return False

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return False

if __name__ == "__main__":
    test_tickers = ["7203.T", "9348.T", "285A.T"]
    for t in test_tickers:
        check_jsf_data(t)
