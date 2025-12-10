#!/usr/bin/env python3
"""
LLM による Dify DSL 差分解析スクリプト

差分を LLM に渡して重要度を判定し、人間が読みやすい説明を生成します。

Usage:
    python scripts/llm_diff_analyzer.py <diff.txt>

Environment Variables:
    OPENAI_API_KEY: OpenAI API キー（必須）
    LLM_MODEL: 使用するモデル（デフォルト: gpt-4o-mini）
"""

import os
import sys
import json
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("❌ Error: openai package is not installed.", file=sys.stderr)
    print("Install it with: pip install openai", file=sys.stderr)
    sys.exit(1)


SYSTEM_PROMPT = """あなたは Dify DSL の差分を解析する専門家です。

# 無視すべき差分（UI メタデータ）
- position, positionAbsolute (ノード座標)
- width, height (ノードサイズ)
- selected (UI 選択状態)
- zIndex (表示順)
- viewport (canvas 表示位置)
- sourcePosition, targetPosition (エッジ接続位置)

これらは「見栄えの変更」であり、処理に影響しないため無視してください。

# 重要な差分（処理に影響）
- nodes[].data.model.* (AI モデル設定)
- nodes[].data.prompt_template (プロンプト内容)
- nodes[].data.completion_params (生成パラメータ)
- edges[] の追加・削除 (ワークフロー接続)
- features.*.enabled (機能 ON/OFF)
- variables, environment_variables (変数定義)
- dependencies[] (プラグイン依存)

# 解析時の必須要件

1. **具体的な値を抽出**
   - 変更前の値（Before）と変更後の値（After）を明示
   - 例: "gemini-2.5-flash-preview-05-20 → gemini-2.5-flash"

2. **変更箇所数をカウント**
   - 同じ変更が複数箇所にある場合は件数を明記
   - 例: "10個のLLMノードで変更"

3. **統計情報を計算**
   - 差分の総行数（+ と - で始まる行）
   - 追加行数（+ で始まる行）
   - 削除行数（- で始まる行）
   - 影響を受けるノード数（title フィールドの変更）
   - 影響を受けるエッジ数（edges 配列の変更）

4. **パターンを検出**
   - 一括変更の可能性（同じ変更が複数箇所）
   - 関連する変更のグループ化

5. **具体的なアクションを提示**
   - チェックリスト形式で"何を確認すべきか"
   - "なぜその確認が必要か"の理由

# 出力形式
JSON 形式で以下の構造を返してください：

{
  "summary": "変更内容の要約（日本語、1-2文、具体的な技術用語を含める）",
  "statistics": {
    "total_diff_lines": 140,
    "added_lines": 95,
    "removed_lines": 45,
    "affected_nodes": 10,
    "affected_edges": 5
  },
  "changes": [
    {
      "type": "added|modified|removed",
      "impact": "high|medium|low",
      "area": "model|prompt|features|graph|config|dependencies|variables",
      "description": "具体的な変更内容（Before → After の形式で記載）",
      "before_value": "変更前の具体的な値（該当する場合）",
      "after_value": "変更後の具体的な値（該当する場合）",
      "count": 1,
      "action": "要レビュー|確認推奨|無視可"
    }
  ],
  "patterns": [
    {
      "description": "検出されたパターン（例: 一括変更、プロバイダー移行）",
      "occurrences": 10
    }
  ],
  "overall_impact": "high|medium|low",
  "recommendation": {
    "immediate_actions": [
      "即座に確認すべき項目（チェックリスト形式）"
    ],
    "review_questions": [
      "レビュー時に確認すべき質問"
    ]
  }
}
"""


def analyze_diff_with_llm(diff_text: str, model: str = "gpt-4o-mini") -> dict:
    """
    LLM で差分を解析

    Args:
        diff_text: 差分テキスト
        model: 使用する LLM モデル

    Returns:
        解析結果の辞書
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    client = OpenAI(api_key=api_key)

    print(f"🤖 Analyzing diff with {model}...")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"以下の Dify DSL の差分を解析してください：\n\n```diff\n{diff_text}\n```"}
            ],
            temperature=0.3,  # 一貫性のある出力のため低めに設定
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        print(f"✅ Analysis complete")
        print(f"📊 Tokens used: {response.usage.total_tokens}")

        return result

    except Exception as e:
        print(f"❌ Error during LLM analysis: {e}", file=sys.stderr)
        raise


def format_analysis_as_markdown(analysis: dict, diff_text: str) -> str:
    """
    解析結果を Markdown 形式に整形

    Args:
        analysis: LLM からの解析結果
        diff_text: 元の差分テキスト

    Returns:
        Markdown 形式の文字列
    """
    # Impact のアイコン
    impact_icons = {
        "high": "🔴",
        "medium": "🟡",
        "low": "🟢"
    }

    # Type のアイコン
    type_icons = {
        "added": "➕",
        "modified": "📝",
        "removed": "➖"
    }

    overall_icon = impact_icons.get(analysis.get("overall_impact", "low"), "⚪")

    md = f"""## 🔍 Dify DSL 差分解析レポート

### {overall_icon} 総合影響度: {analysis.get('overall_impact', 'unknown').upper()}

**要約**: {analysis.get('summary', '差分が検出されました')}

---

"""

    # 統計情報の追加
    stats = analysis.get('statistics', {})
    if stats:
        md += f"""### 📊 変更統計

- **総差分行数**: {stats.get('total_diff_lines', 'N/A')} 行
- **追加**: {stats.get('added_lines', 'N/A')} 行
- **削除**: {stats.get('removed_lines', 'N/A')} 行
- **影響を受けるノード数**: {stats.get('affected_nodes', 'N/A')} 個
- **影響を受けるエッジ数**: {stats.get('affected_edges', 'N/A')} 個

---

"""

    md += """### 📋 変更一覧

"""

    changes = analysis.get('changes', [])
    if not changes:
        md += "_変更が検出されませんでした_\n\n"
    else:
        for i, change in enumerate(changes, 1):
            type_icon = type_icons.get(change.get('type', ''), '❓')
            impact_icon = impact_icons.get(change.get('impact', 'low'), '⚪')

            md += f"""#### {i}. {type_icon} {change.get('type', 'unknown').upper()} - {change.get('area', 'unknown')}

- **影響度**: {impact_icon} {change.get('impact', 'unknown').upper()}
- **説明**: {change.get('description', '説明なし')}
"""

            # Before/After の値を表示
            if change.get('before_value') or change.get('after_value'):
                md += "\n```diff\n"
                if change.get('before_value'):
                    md += f"- {change.get('before_value')}\n"
                if change.get('after_value'):
                    md += f"+ {change.get('after_value')}\n"
                md += "```\n"

            # 変更件数を表示
            if change.get('count', 1) > 1:
                md += f"\n- **変更箇所数**: {change.get('count')} 箇所\n"

            md += f"- **アクション**: {change.get('action', '確認推奨')}\n\n"

    # パターン分析の追加
    patterns = analysis.get('patterns', [])
    if patterns:
        md += """---

### 🔍 検出されたパターン

"""
        for pattern in patterns:
            md += f"- **{pattern.get('description', '不明なパターン')}**: {pattern.get('occurrences', 0)} 箇所\n"
        md += "\n"

    md += """---

### 💡 推奨アクション

"""

    recommendation = analysis.get('recommendation', {})
    if isinstance(recommendation, dict):
        # 新しい構造化された推奨アクション
        immediate_actions = recommendation.get('immediate_actions', [])
        if immediate_actions:
            md += "#### 🚨 即座に確認すべき項目\n\n"
            for action in immediate_actions:
                md += f"- [ ] {action}\n"
            md += "\n"

        review_questions = recommendation.get('review_questions', [])
        if review_questions:
            md += "#### 📝 レビュー時の確認事項\n\n"
            for question in review_questions:
                md += f"- {question}\n"
            md += "\n"
    else:
        # 古い形式（文字列）への後方互換性
        md += f"{recommendation}\n\n"

    md += f"""---

<details>
<summary>📄 元の差分を表示</summary>

```diff
{diff_text}
```

</details>

---

_🤖 この解析は LLM により自動生成されました_
"""

    return md


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <diff.txt>", file=sys.stderr)
        print(f"\nExample:", file=sys.stderr)
        print(f"  {sys.argv[0]} diff.txt", file=sys.stderr)
        sys.exit(1)

    diff_path = Path(sys.argv[1])

    # 差分ファイルの存在確認
    if not diff_path.exists():
        print(f"❌ Error: Diff file not found: {diff_path}", file=sys.stderr)
        sys.exit(1)

    # 差分ファイルの読み込み
    try:
        with diff_path.open('r', encoding='utf-8') as f:
            diff_text = f.read()
    except Exception as e:
        print(f"❌ Error: Failed to read diff file: {e}", file=sys.stderr)
        sys.exit(1)

    # 空の差分をチェック
    if not diff_text.strip():
        print("ℹ️  No diff detected (empty file)")
        result = {
            "summary": "差分が検出されませんでした",
            "changes": [],
            "overall_impact": "low",
            "recommendation": "変更はありません。"
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    # LLM で解析
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    try:
        analysis = analyze_diff_with_llm(diff_text, model)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

    # JSON 出力
    print("\n" + "="*60)
    print("JSON Output:")
    print("="*60)
    print(json.dumps(analysis, ensure_ascii=False, indent=2))

    # Markdown 出力
    markdown = format_analysis_as_markdown(analysis, diff_text)
    output_path = diff_path.parent / f"{diff_path.stem}_analysis.md"

    try:
        with output_path.open('w', encoding='utf-8') as f:
            f.write(markdown)
        print(f"\n✅ Markdown report saved to: {output_path}")
    except Exception as e:
        print(f"⚠️  Warning: Failed to save markdown: {e}", file=sys.stderr)

    # GitHub Actions の output に設定するための情報を出力
    if os.getenv("GITHUB_OUTPUT"):
        try:
            with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
                f.write(f"analysis_json<<EOF\n{json.dumps(analysis, ensure_ascii=False)}\nEOF\n")
                f.write(f"overall_impact={analysis.get('overall_impact', 'low')}\n")
        except Exception as e:
            print(f"⚠️  Warning: Failed to write to GITHUB_OUTPUT: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
