import yfinance as yf
import json

def test_kr_tickers():
    test_watchlist = ['005930.KS', '000660.KS', '247540.KQ', '^KS11', '^KQ11']
    print(f"Testing tickers: {test_watchlist}")
    
    for ticker_symbol in test_watchlist:
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                print(f"✅ {ticker_symbol}: {hist['Close'].iloc[-1]} (Volume: {hist['Volume'].iloc[-1]})")
                # Test news fetching
                news = ticker.news
                if news:
                    print(f"   - News found: {news[0]['title']}")
                else:
                    print(f"   - No news found for {ticker_symbol}")
            else:
                print(f"❌ {ticker_symbol}: No data found")
        except Exception as e:
            print(f"⚠️ {ticker_symbol} failed: {e}")

if __name__ == "__main__":
    test_kr_tickers()
