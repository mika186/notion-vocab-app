import requests

NOTION_TOKEN = "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"
DATABASE_ID = "213d8fdd77d580bfbdf5e6229ff98fa4"  # ← 直近の正しいID

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

url = f"https://api.notion.com/v1/databases/{DATABASE_ID}"

response = requests.get(url, headers=headers)

data = response.json()

print("📋 あなたのNotionデータベースのプロパティ一覧:")
for name, info in data["properties"].items():
    print(f"- 表示名: {info.get('name')} / 内部名: {name} / 型: {info['type']}")
