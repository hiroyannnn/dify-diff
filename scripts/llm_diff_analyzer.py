#!/usr/bin/env python3
"""
LLM による Dify DSL 差分解析スクリプト

差分を LLM に渡して重要度を判定し、人間が読みやすい説明を生成します。

Usage:
    python scripts/llm_diff_analyzer.py <diff.txt> [--before <old.yml> --after <new.yml>]

Environment Variables:
    OPENAI_API_KEY: OpenAI API キー（必須）
    LLM_MODEL: 使用するモデル（デフォルト: gpt-5.1）
"""

import argparse
import os
import re
import sys
import json
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    print("❌ Error: openai package is not installed.", file=sys.stderr)
    print("Install it with: pip install openai", file=sys.stderr)
    sys.exit(1)

try:
    from ruamel.yaml import YAML
except ImportError:
    print("❌ Error: ruamel.yaml package is not installed.", file=sys.stderr)
    print("Install it with: pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)


SYSTEM_PROMPT = """あなたは Dify DSL の差分を解析する専門家です。
変更内容を事実ベースで分かりやすく整理し、ユーザーが YAML diff を読む前に概要とレビュー観点の変更点を把握できるようにしてください。

# 無視すべき差分（UI メタデータ）
- position, positionAbsolute (ノード座標)
- width, height (ノードサイズ)
- selected (UI 選択状態)
- zIndex (表示順)
- viewport (canvas 表示位置)
- sourcePosition, targetPosition (エッジ接続位置)

これらは「見栄えの変更」であり、処理に影響しないため無視してください。

# 重要な差分（処理に影響）
- workflow.graph.nodes[].data.model.* (AI モデル設定)
- workflow.graph.nodes[].data.prompt_template (プロンプト内容)
- workflow.graph.nodes[].data.completion_params (生成パラメータ)
- workflow.graph.edges[] (ワークフロー接続)
- workflow.features.*.enabled (機能 ON/OFF)
- workflow.conversation_variables, workflow.environment_variables (変数定義)
- dependencies[] (プラグイン依存)

# 解析時の必須要件

1. **YAMLパスを明記**
   - 変更箇所をYAMLパス表記で示す
     - 単一変更: `workflow.graph.edges[0]`, `workflow.graph.nodes[2].data.type`
     - まとめ変更: `workflow.graph.nodes[].data.model.name` のように配列をまとめて示す
   - 単一変更では配列のインデックスは実際の位置を示す（0始まり）
   - ネストした構造も明確に表現

2. **差分の行番号を抽出**
   - diff の @@ 行から行番号情報を取得
   - 各変更がファイルの何行目付近にあるかを明記
   - 例: "L142-L145" のような形式で表示

3. **具体的な値を抽出**
   - `changes.before_value` と `changes.after_value` に具体値を入れる
   - `changes.description` では影響が伝わる短い説明を添える

4. **変更箇所数をカウント**
   - 同様の変更が複数箇所にある場合は `count` で件数を明記

5. **レビュー用の要点を作成**
   - 要約より詳細で、変更一覧より抽象度を上げる
   - 変更点を 3〜10 件の箇条書きで整理
   - 変更の対象範囲（YAML パスのプレフィックス等）を明記
   - 単なる差分列挙は避け、PR レビューで論点になる単位にまとめる

6. **変更一覧は適度にまとめる**
   - 1行単位の羅列は避け、同種の変更は1項目にまとめる

# 出力形式
JSON 形式で以下の構造を返してください：

⚠️ **重要**:
- アドバイスや推奨事項は含めないでください。事実のみを記載してください。
- yaml_path は具体的な階層構造を示してください（例: workflow.graph.nodes[0].data.model.name）

{
  "summary": "変更内容の要約（日本語、1-2文、具体的な技術用語を含める）",
  "review_points": [
    {
      "title": "レビュー用の変更点（短く）",
      "details": "変更の中身を1-2文で具体化（Before/Afterや影響範囲が分かるように）",
      "scope": "主な対象範囲の YAML パス（プレフィックス可）",
      "count": 1
    }
  ],
  "changes": [
    {
      "type": "added|modified|removed",
      "yaml_path": "workflow.graph.nodes[0].data.model.name",
      "location": "変更箇所の行番号（例: L142-L145）",
      "description": "具体的な変更内容（短い説明）",
      "before_value": "変更前の具体的な値（該当する場合）",
      "after_value": "変更後の具体的な値（該当する場合）",
      "count": 1
    }
  ]
}
"""

IGNORED_KEYS = {
    "position",
    "positionAbsolute",
    "width",
    "height",
    "selected",
    "zIndex",
    "viewport",
    "sourcePosition",
    "targetPosition",
}


def strip_ignored(value):
    if isinstance(value, dict):
        return {
            key: strip_ignored(val)
            for key, val in value.items()
            if key not in IGNORED_KEYS
        }
    if isinstance(value, list):
        return [strip_ignored(item) for item in value]
    return value


def load_yaml(path: Path):
    yaml = YAML(typ="safe")
    with path.open('r', encoding='utf-8') as f:
        return yaml.load(f) or {}


def get_graph_data(data):
    workflow = data.get("workflow", {}) if isinstance(data, dict) else {}
    graph = workflow.get("graph", {}) if isinstance(workflow, dict) else {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    return nodes if isinstance(nodes, list) else [], edges if isinstance(edges, list) else []


def node_label(node_id: str, node: dict) -> str:
    data = node.get("data", {}) if isinstance(node, dict) else {}
    title = data.get("title")
    node_type = data.get("type")
    if title and node_type:
        label = f"{title}<br/>({node_type})"
    elif title:
        label = str(title)
    elif node_type:
        label = f"{node_type}"
    else:
        label = str(node_id)
    return label.replace('"', "'").strip()


def mermaid_id(raw_id: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", str(raw_id))


def edge_key(edge: dict) -> str:
    if not isinstance(edge, dict):
        return ""
    edge_id = edge.get("id")
    if edge_id:
        return str(edge_id)
    source = edge.get("source", "")
    target = edge.get("target", "")
    return f"{source}->{target}"


def build_change_diagram(before_data: dict, after_data: dict) -> Optional[str]:
    old_nodes_list, old_edges_list = get_graph_data(before_data)
    new_nodes_list, new_edges_list = get_graph_data(after_data)

    old_nodes = {str(n.get("id")): n for n in old_nodes_list if isinstance(n, dict) and n.get("id") is not None}
    new_nodes = {str(n.get("id")): n for n in new_nodes_list if isinstance(n, dict) and n.get("id") is not None}

    old_edges = {edge_key(e): e for e in old_edges_list if edge_key(e)}
    new_edges = {edge_key(e): e for e in new_edges_list if edge_key(e)}

    old_node_ids = set(old_nodes.keys())
    new_node_ids = set(new_nodes.keys())

    added_nodes = new_node_ids - old_node_ids
    removed_nodes = old_node_ids - new_node_ids
    common_nodes = old_node_ids & new_node_ids

    modified_nodes = {
        node_id
        for node_id in common_nodes
        if strip_ignored(old_nodes.get(node_id)) != strip_ignored(new_nodes.get(node_id))
    }

    old_edge_keys = set(old_edges.keys())
    new_edge_keys = set(new_edges.keys())

    added_edges = new_edge_keys - old_edge_keys
    removed_edges = old_edge_keys - new_edge_keys
    common_edges = old_edge_keys & new_edge_keys

    modified_edges = {
        edge_id
        for edge_id in common_edges
        if strip_ignored(old_edges.get(edge_id)) != strip_ignored(new_edges.get(edge_id))
    }

    if not (added_nodes or removed_nodes or modified_nodes or added_edges or removed_edges or modified_edges):
        return None

    context_edges = set()
    if added_nodes or modified_nodes:
        for edge in new_edges_list:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source in added_nodes or source in modified_nodes or target in added_nodes or target in modified_nodes:
                key = edge_key(edge)
                if key:
                    context_edges.add(key)
    if removed_nodes:
        for edge in old_edges_list:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source in removed_nodes or target in removed_nodes:
                key = edge_key(edge)
                if key:
                    context_edges.add(key)

    edges_to_draw = set().union(added_edges, removed_edges, modified_edges, context_edges)
    edges_to_draw_list = []
    for key in sorted(edges_to_draw):
        edge = old_edges.get(key) if key in removed_edges else new_edges.get(key) or old_edges.get(key)
        if edge:
            edges_to_draw_list.append((key, edge))

    nodes_to_draw = set(added_nodes) | set(removed_nodes) | set(modified_nodes)
    for _, edge in edges_to_draw_list:
        source = edge.get("source")
        target = edge.get("target")
        if source is not None:
            nodes_to_draw.add(str(source))
        if target is not None:
            nodes_to_draw.add(str(target))

    if not nodes_to_draw:
        return None

    node_lines = []
    for node_id in sorted(nodes_to_draw):
        node = new_nodes.get(node_id) or old_nodes.get(node_id)
        if not node:
            continue
        label = node_label(node_id, node)
        node_class = ""
        if node_id in added_nodes:
            node_class = "added"
        elif node_id in removed_nodes:
            node_class = "removed"
        elif node_id in modified_nodes:
            node_class = "modified"
        line = f'{mermaid_id(node_id)}["{label}"]'
        if node_class:
            line += f":::{node_class}"
        node_lines.append(line)

    edge_lines = []
    link_styles = []
    edge_index = 0
    for key, edge in edges_to_draw_list:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source or not target:
            continue
        edge_lines.append(f"{mermaid_id(source)} --> {mermaid_id(target)}")
        style_class = None
        if key in added_edges:
            style_class = "added"
        elif key in removed_edges:
            style_class = "removed"
        elif key in modified_edges:
            style_class = "modified"
        if style_class:
            link_styles.append((edge_index, style_class))
        edge_index += 1

    diagram_lines = [
        "flowchart LR",
        "classDef added fill:#D1FAE5,stroke:#10B981,color:#065F46;",
        "classDef removed fill:#FEE2E2,stroke:#EF4444,color:#7F1D1D,stroke-dasharray: 5 5;",
        "classDef modified fill:#FEF3C7,stroke:#F59E0B,color:#78350F;",
    ]
    diagram_lines.extend(node_lines)
    diagram_lines.extend(edge_lines)

    for index, style_class in link_styles:
        if style_class == "added":
            diagram_lines.append(f"linkStyle {index} stroke:#10B981,stroke-width:2px;")
        elif style_class == "removed":
            diagram_lines.append(
                f"linkStyle {index} stroke:#EF4444,stroke-width:2px,stroke-dasharray: 5 5;"
            )
        elif style_class == "modified":
            diagram_lines.append(f"linkStyle {index} stroke:#F59E0B,stroke-width:2px;")

    return "\n".join(diagram_lines)


def analyze_diff_with_llm(diff_text: str, model: str = "gpt-5.1") -> dict:
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


def format_analysis_as_markdown(analysis: dict, diagram: Optional[str] = None) -> str:
    """
    解析結果を Markdown 形式に整形

    Args:
        analysis: LLM からの解析結果

    Returns:
        Markdown 形式の文字列
    """
    # Type のアイコン
    type_icons = {
        "added": "➕",
        "modified": "📝",
        "removed": "➖"
    }

    md = f"""## 🔍 Dify DSL 差分解析レポート

**要約**: {analysis.get('summary', '差分が検出されました')}

---

"""

    review_points = analysis.get('review_points', [])
    if review_points:
        md += "### 🧭 変更の要点\n\n"
        for point in review_points:
            title = point.get('title', '変更点')
            details = point.get('details')
            scope = point.get('scope')
            count = point.get('count')

            line = f"- **{title}**"
            if scope:
                line += f" (`{scope}`)"
            if isinstance(count, int) and count > 1:
                line += f" ×{count}"
            if details:
                line += f": {details}"
            md += f"{line}\n"
        md += "\n---\n\n"

    if diagram:
        md += "### 🗺️ 変更フロー図\n\n"
        md += "```mermaid\n"
        md += diagram
        md += "\n```\n\n---\n\n"

    md += """<details>
<summary>📋 変更一覧を表示</summary>

### 📋 変更一覧

"""

    changes = analysis.get('changes', [])
    if not changes:
        md += "_変更が検出されませんでした_\n\n"
    else:
        for i, change in enumerate(changes, 1):
            type_icon = type_icons.get(change.get('type', ''), '❓')
            yaml_path = change.get('yaml_path', change.get('area', 'unknown'))  # 後方互換性のため area もフォールバック

            md += f"""#### {i}. {type_icon} {change.get('type', 'unknown').upper()} - `{yaml_path}`

"""

            # 行番号の表示
            if change.get('location'):
                md += f"**行番号**: {change.get('location')}\n\n"

            md += f"{change.get('description', '説明なし')}\n"

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

            md += "\n"

    md += "</details>\n\n"

    md += """---

_🤖 この解析は LLM により自動生成されました_
"""

    return md


def main():
    parser = argparse.ArgumentParser(description="Analyze Dify DSL diff with LLM")
    parser.add_argument("diff_path", help="Path to diff file")
    parser.add_argument("--before", help="Path to old Dify DSL YAML")
    parser.add_argument("--after", help="Path to new Dify DSL YAML")
    args = parser.parse_args()

    diff_path = Path(args.diff_path)
    before_path = Path(args.before) if args.before else None
    after_path = Path(args.after) if args.after else None

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
            "overall_impact": "low"
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    # LLM で解析
    model = os.getenv("LLM_MODEL", "gpt-5.1")

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

    diagram = None
    if before_path or after_path:
        if not (before_path and after_path):
            print("⚠️  Warning: --before と --after の両方が必要です。図の生成はスキップします。")
        elif not before_path.exists():
            print(f"⚠️  Warning: before file not found: {before_path}")
        elif not after_path.exists():
            print(f"⚠️  Warning: after file not found: {after_path}")
        else:
            try:
                before_data = load_yaml(before_path)
                after_data = load_yaml(after_path)
                diagram = build_change_diagram(before_data, after_data)
                if diagram:
                    print("🗺️  Diagram generated")
            except Exception as e:
                print(f"⚠️  Warning: Failed to generate diagram: {e}", file=sys.stderr)

    # Markdown 出力
    markdown = format_analysis_as_markdown(analysis, diagram)
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

# trigger
