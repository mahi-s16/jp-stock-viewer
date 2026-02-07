import requests
from bs4 import BeautifulSoup
import re

def get_margin_balance(ticker):
    url = f"https://finance.yahoo.co.jp/quote/{ticker}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        
        def get_val(label):
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

        date_span = soup.find("span", class_=lambda c: c and "MarginTransactionInformation__date" in c)
        date_str = date_span.get_text(strip=True) if date_span else ""
        date_str = date_str.replace("(", "").replace(")", "")

        return {
            "buy": get_val("信用買残"),
            "sell": get_val("信用売残"),
            "ratio": get_val("信用倍率"),
            "date": date_str
        }

    except Exception as e:
        print(f"Margin Error {ticker}: {e}")
        return {"buy": "-", "sell": "-", "ratio": "-", "date": ""}

if __name__ == "__main__":
    test_tickers = ["285A.T", "9348.T", "7203.T"]
    for t in test_tickers:
        print(f"Ticker: {t}")
        print(get_margin_balance(t))
