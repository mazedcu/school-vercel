import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/', timeout=5) as response:
        print(f"Status Code: {response.status}")
        content = response.read()
        print(f"Content Length: {len(content)}")
        print(f"Snippet: {content[:200].decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")
