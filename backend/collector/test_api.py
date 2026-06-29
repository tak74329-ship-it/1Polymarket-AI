import requests
import json

url = "https://gamma-api.polymarket.com/markets?limit=1"

r = requests.get(url, timeout=20)
r.raise_for_status()

data = r.json()

print("===== 返回类型 =====")
print(type(data))

print("\n===== 第一条数据 =====")
print(json.dumps(data[0], indent=2, ensure_ascii=False))
