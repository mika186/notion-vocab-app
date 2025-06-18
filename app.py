import os
import re
import json
import requests
from flask import Flask, request
from notion_client import Client
import openai  # ← ここ修正
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

notion = Client(auth=NOTION_API_KEY)
openai.api_key = OPENAI_API_KEY  # ← ここ修正

print("✅ NOTION_DATABASE_ID:", NOTION_DATABASE_ID)
print("✅ OPENAI_API_KEY:", "あり" if OPENAI_API_KEY else "なし")
print("✅ NOTION_API_KEY:", "あり" if NOTION_API_KEY else "なし")

app = Flask(__name__)

PROPERTY_MAP = {
    "頻度": "頻度",
    "難易度": "難易度",
    "品詞": "品詞",
    "フォーマル度": "フォーマル度",
    "カジュアル度": "カジュアル度",
}

CALLOUT_SECTIONS = [
    "発音", "意味", "語源", "語感", "コロケーション", "例文", "自由記述", "関連語"
]

SECTION_ICON_COLOR = {
    "発音": ("🔊", "gray_background"),
    "意味": ("📖", "purple_background"),
    "語源": ("🧬", "gray_background"),
    "語感": ("💭", "gray_background"),
    "コロケーション": ("📌", "green_background"),
    "例文": ("📝", "blue_background"),
    "自由記述": ("🧠", "gray_background"),
    "関連語": ("📚", "gray_background"),
}

def ask_gpt_about(word):
    system_msg = """
あなたは語源や英語教育に精通した英語教師です。
以下の英単語について、次の13の観点で簡潔に出力してください：
頻度（よく使う、そこそこ使う、たまに使わない、あまり使わない）、
難易度（A1〜C2のCEFR基準）、品詞（形容詞、動詞、名詞、副詞など）、
フォーマル度（〇、△、×）、カジュアル度（〇、△、×）、
発音記号（例：/əˈplɒd/）、意味（簡潔な日本語訳）、
語源（英語またはラテン語などからの由来）、語感（ネイティブの感覚的な意味合いやニュアンス）、
代表的なコロケーション（5個＋日本語訳）、
代表的な例文（3個＋日本語訳。英文と訳は段落を分けて）、
自由記述（補足情報や注意点、活用など）、
関連語（派生語・類義語・反意語に分類、各カテゴリに1つ以上＋各語に2〜3行の簡潔な解説を含める）
形式：
---
頻度:
難易度:
品詞:
フォーマル度:
カジュアル度:
発音:
意味:
語源:
語感:
コロケーション:
例文:
自由記述:
関連語:
---
    """
    print("🧠 ChatGPTに問い合わせ中...")
    response = openai.ChatCompletion.create(  # ← ここ修正
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": word}
        ]
    )
    return response.choices[0].message.content.strip()

def parse_sections(gpt_text):
    keys = ["頻度", "難易度", "品詞", "フォーマル度", "カジュアル度", "発音", "意味", "語源", "語感", "コロケーション", "例文", "自由記述", "関連語"]
    result = {}
    current_key = None
    buffer = []
    for line in gpt_text.splitlines():
        if any(line.startswith(f"{key}:") for key in keys):
            if current_key:
                result[current_key] = "\n".join(buffer).strip()
            current_key, rest = line.split(":", 1)
            buffer = [rest.strip()]
        else:
            buffer.append(line.strip())
    if current_key:
        result[current_key] = "\n".join(buffer).strip()
    return result

def update_notion_properties(page_id, fields):
    props = {}
    for key, value in fields.items():
        if key in ["頻度", "難易度", "フォーマル度", "カジュアル度"]:
            props[PROPERTY_MAP[key]] = {"select": {"name": value}}
        elif key == "品詞":
            tags = [s.strip() for s in value.split("、")]
            props[PROPERTY_MAP[key]] = {"multi_select": [{"name": t} for t in tags]}
    notion.pages.update(page_id=page_id, properties=props)

def format_example_sentences(raw_text):
    lines = raw_text.strip().splitlines()
    formatted = []
    for i in range(0, len(lines), 2):
        if i+1 < len(lines):
            formatted.append(f"{lines[i].strip()}\n{lines[i+1].strip()}\n")
    return "\n".join(formatted).strip()

def render_related_words(raw_text):
    blocks = []
    for label, emoji in [("派生語", "📘"), ("類義語", "📗"), ("反意語", "📕")]:
        match = re.search(rf"{label}[:：](.*?)(?=\n[A-Za-z\u3040-\u30FF\u4E00-\u9FFF]+[:：]|\Z)", raw_text, re.DOTALL)
        content = match.group(1).strip() if match else "該当情報が取得できませんでした。"
        content = f"{emoji} {label}\n{content.strip()}"
        blocks.append(content)
    return "\n\n".join(blocks)

def append_callouts(page_id, content_map):
    children = []
    for section in CALLOUT_SECTIONS:
        if section in content_map:
            content = content_map[section]
            if section == "例文":
                content = format_example_sentences(content)
            if section == "関連語":
                content = render_related_words(content)
            icon, color = SECTION_ICON_COLOR.get(section, ("💡", "default"))
            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": icon},
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": f"{section}：\n{content}"}
                        }
                    ],
                    "color": color
                }
            })
    if children:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        res = requests.patch(url, headers=headers, data=json.dumps({"children": children}))
        print("📤 Callouts result:", res.status_code, res.text)

@app.route("/add_word")
def add_word():
    word = request.args.get("word")
    print(f"📥 リクエスト受信: word='{word}'")
    gpt_text = ask_gpt_about(word)
    sections = parse_sections(gpt_text)

    new_page = notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={
            "名前": {
                "title": [
                    {"type": "text", "text": {"content": word}}
                ]
            }
        }
    )
    page_id = new_page["id"].replace("-", "")
    update_notion_properties(page_id, sections)
    append_callouts(page_id, sections)
    return f"✅ '{word}' をNotionに追加しました！"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
