import httpx
import json

def test_coinglass():
    url = "https://fapi.coinglass.com/api/v1/funding_rate/rank?type=u&interval=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(json.dumps(data, indent=2)[:1000])
        else:
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_coinglass()
