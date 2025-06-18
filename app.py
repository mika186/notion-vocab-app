import os
import re
import json
import requests
from flask import Flask, request
from notion_client import Client as NotionClient
from openai import OpenAI
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv()

# 環境変数からAPIキーを取得
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print(f"✅ NOTION_DATABASE_ID: {NOTION_DATABASE_ID or 'None'}")
print(f"✅ OPENAI_API_KEY: {'あり' if OPENAI_API_KEY else 'なし'}")
print(f"✅ NOTION_API_KEY: {'あり' if NOTION_API_KEY else 'なし'}")

# クライアント初期化
notion = NotionClient(auth=NOTION_API_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)

# Flask アプリ初期化
app = Flask(__name__)

# --- ChatGPT への問い合わせ ---
def ask_gpt_about(word):
    system_msg = """
あなたは語源や英語教育に精通した英語教師です。
以下の英単語について、次の13の観点で簡潔に出力してください：

1. 頻度（4択：よく使う／そこそこ使う／たまに使う／あまり使わない）
2. 難易度（CEFR: A1～C2）
3. 品詞（形容詞・動詞・名詞・副詞のマルチセレクト）
4. カジュアル度（〇・△・×の三択）
5. フォーマル度（〇・△・×の三択）
6. 発音記号
7. 意味（簡潔に）
8. 語源（できるだけ）
9. 語感（ネイティブ視点の語の印象・雰囲気）
10. コロケーション（使用頻度の高いもの5つ、日本語訳付きで）
11. 例文（使用頻度の高いもの3つ、日本語訳付きで）
12. 自由記述（他に知っておくべき重要事項があれば）
13. 関連語（派生語・類義語・反意語に分け、意味付きで）

フォーマットは Markdownではなく、以下のようにしてください：
タイトル: 内容（または改行して内容）
余計な説明文は不要です。
    """

    print("📥 リクエスト受信:", word)
    print("🧠 ChatGPTに問い合わせ中...")

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": word}
        ]
    )

    return response.choices[0].message.content.strip()

# --- テキストからラベル抽出 ---
def extract_section(label, raw_text):
    match = re.search(f"{label}[:：](.*?)(?=\n[A-Za-z\u3040-\u30FF\u4E00-\u9FFF]+[:：]|\Z)", raw_text, re.DOTALL)
    return match.group(1).strip() if match else ""

# --- Notionページ追加 ---
def create_notion_page(word, gpt_text):
    properties = {
        "Name": {"title": [{"text": {"content": word}}]},
        "頻度": {"select": {"name": extract_section("頻度", gpt_text)}},
        "難易度": {"select": {"name": extract_section("難易度", gpt_text)}},
        "品詞": {
            "multi_select": [{"name": p.strip()} for p in extract_section("品詞", gpt_text).split("・")]
        },
        "カジュアル度": {"select": {"name": extract_section("カジュアル度", gpt_text)}},
        "フォーマル度": {"select": {"name": extract_section("フォーマル度", gpt_text)}},
    }

    # 本文コールアウトのためのヘルパー関数
    def make_callout_block(title, content, emoji, color="gray_background"):
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"emoji": emoji},
                "rich_text": [
                    {"type": "text", "text": {"content": f"{title}：\n{content}"}}
                ],
                "color": color,
            }
        }

    children = [
        make_callout_block("発音", extract_section("発音", gpt_text), "🔈"),
        make_callout_block("意味", extract_section("意味", gpt_text), "🟣", "purple_background"),
        make_callout_block("語源", extract_section("語源", gpt_text), "🧬"),
        make_callout_block("語感", extract_section("語感", gpt_text), "🎨"),
        make_callout_block("コロケーション", extract_section("コロケーション", gpt_text), "🧩", "green_background"),
        make_callout_block("例文", extract_section("例文", gpt_text), "📘", "blue_background"),
        make_callout_block("自由記述", extract_section("自由記述", gpt_text), "📝"),
        make_callout_block("関連語", extract_section("関連語", gpt_text), "🔗"),
    ]

    notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties=properties,
        children=children
    )

# --- ルートエンドポイント ---
@app.route("/")
def index():
    return "Notion Vocabulary App is running!"

# --- 単語追加エンドポイント ---
@app.route("/add_word", methods=["GET"])
def add_word():
    word = request.args.get("word")
    if not word:
        return "単語が指定されていません", 400

    try:
        gpt_text = ask_gpt_about(word)
        create_notion_page(word, gpt_text)
        return f"✅ {word} をNotionに追加しました！"
    except Exception as e:
        print("❌ エラー:", e)
        return f"エラーが発生しました: {e}", 500

# --- ローカル用 ---
if __name__ == "__main__":
    app.run(debug=True)
