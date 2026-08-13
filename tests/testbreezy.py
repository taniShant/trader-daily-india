from breeze_connect import BreezeConnect

# Initialize with your credentials
breeze = BreezeConnect(api_key="O6731z39in79bV=1U53K615238Q47GX7")

# Generate session with your new token
breeze.generate_session(
    api_secret="59040P16966s175171c&OZ2370138J32",
    session_token="9db40266-0c9b-4ebb-a751-953e2c0d0d44"
)

# Test - Get quotes for a stock
try:
    quotes = breeze.get_quotes(stock_code="RELIND", exchange_code="NSE")
    print("✅ Connection successful!")
    print(quotes)
except Exception as e:
    print(f"❌ Error: {e}")
