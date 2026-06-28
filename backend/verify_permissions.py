import json
import urllib.request
import urllib.error

def get_token(username, password):
    url = "http://127.0.0.1:8000/api/token/"
    data = {"username": username, "password": password}
    headers = {"Content-Type": "application/json", "Host": "sidhutenant.localhost:8000"}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access"]

def patch_user(token, user_id, first_name):
    url = f"http://127.0.0.1:8000/api/users/{user_id}/"
    data = {"first_name": first_name}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Host": "sidhutenant.localhost:8000"
    }
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def delete_user(token, user_id):
    url = f"http://127.0.0.1:8000/api/users/{user_id}/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": "sidhutenant.localhost:8000"
    }
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# Tokens
admin_token = get_token("Sidhu", "123")
member_token = get_token("newuser", "123")

print("--- Testing Permissions ---")

# 1. Member editing self (ID 2)
status, res = patch_user(member_token, 2, "MemberSelf")
print(f"Member editing self: Status {status}")

# 2. Member editing admin (ID 1)
status, res = patch_user(member_token, 1, "Hacked")
print(f"Member editing admin: Status {status} (Expected 403)")

# 3. Admin editing member (ID 2)
status, res = patch_user(admin_token, 2, "AdminEdited")
print(f"Admin editing member: Status {status}")

# 4. Member deleting self
status, res = delete_user(member_token, 2)
print(f"Member deleting self: Status {status} (Expected 403)")

# 5. Member hitting /me/
url_me = "http://127.0.0.1:8000/api/users/me/"
req_me = urllib.request.Request(url_me, headers={"Authorization": f"Bearer {member_token}", "Host": "sidhutenant.localhost:8000"})
with urllib.request.urlopen(req_me) as resp:
    print(f"Member /me/ check: {resp.read().decode()}")
