import json
import urllib.request
import urllib.error

# Test Login for sidhutenant using Host header mapping
# Testing 'newuser' which is a regular member (not superuser)
url = "http://127.0.0.1:8000/api/token/"
data = {
    "username": "newuser",
    "password": "123"
}

headers = {
    "Content-Type": "application/json",
    "Host": "sidhutenant.localhost:8000"
}

req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")

try:
    with urllib.request.urlopen(req) as response:
        print(f"Status Code: {response.status}")
        print(f"Response: {response.read().decode()}")
except urllib.error.HTTPError as e:
    err_body = e.read().decode()
    print(f"HTTP Error {e.code}: {err_body}")
except Exception as e:
    print(f"Error: {e}")
