import urllib.request
import json

url = "https://www.opdevsystems.xyz/api/sync/"
payload = {
    "token": "opdev_default_secret",
    "logs": [
        {
            "biometric_id": "101",
            "timestamp": "2026-05-12 08:30:00"
        }
    ]
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(url, data=data)
req.add_header('Content-Type', 'application/json')

print(f"Sending request to {url}...")
try:
    with urllib.request.urlopen(req) as response:
        status = response.getcode()
        body = response.read().decode('utf-8')
        print(f"Status Code: {status}")
        print(f"Response: {body}")
except Exception as e:
    print(f"Error: {str(e)}")
