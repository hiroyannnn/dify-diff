#!/usr/bin/env python3
"""
Dify DSL 正規化スクリプト（フォーマット保持版）

UI メタデータを除去し、差分レビューを容易にします。
元の YAML フォーマットをできる限り保持します。

Usage:
    python scripts/normalize_dify.py <input.yml> <output.yml>
"""

import sys
from pathlib import Path
from ruamel.yaml import YAML

# 削除するフィールド（UI メタデータ）
DROP_FIELDS = {
    'position', 'positionAbsolute', 'width', 'height',
    'selected', 'zIndex', 'viewport',
    'sourcePosition', 'targetPosition'
}

# ソートする配列フィールド（順序に意味がないもの）
LIST_SORT_KEYS = {
    'allowed_file_extensions',
    'allowed_file_types',
    'transfer_methods',
    'allowed_file_upload_methods'
}


def normalize_node(node, parent_key=None):
    """
    ノードから UI メタデータを再帰的に削除
    フォーマットを保持するため、in-place で削除

    Args:
        node: YAML データ（dict, list, または primitive）
        parent_key: 親のキー名（配列のソート判定に使用）

    Returns:
        正規化されたデータ
    """
    if isinstance(node, dict):
        # UI フィールドを削除
        keys_to_remove = [k for k in node.keys() if k in DROP_FIELDS]
        for k in keys_to_remove:
            del node[k]

        # 再帰的に処理
        for k, v in node.items():
            node[k] = normalize_node(v, k)

        return node

    elif isinstance(node, list):
        # 順序に意味がない配列をソート
        if parent_key in LIST_SORT_KEYS:
            # 文字列のリストのみソート
            if all(isinstance(x, str) for x in node):
                return sorted(node)

        # リストの各要素を再帰的に処理
        return [normalize_node(item, parent_key) for item in node]

    return node


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.yml> <output.yml>", file=sys.stderr)
        print(f"\nExample:", file=sys.stderr)
        print(f"  {sys.argv[0]} chat.yml chat.norm.yml", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    # 入力ファイルの存在確認
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # YAML 読み込み（roundtrip モード = フォーマット保持）
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 4096  # 長い行の折り返しを防ぐ

    try:
        with input_path.open('r', encoding='utf-8') as f:
            data = yaml.load(f)
    except Exception as e:
        print(f"❌ Error: Failed to load YAML: {e}", file=sys.stderr)
        sys.exit(1)

    # 正規化処理（フォーマットを保持したまま UI フィールドを削除）
    print(f"🔄 Normalizing {input_path}...")
    data = normalize_node(data)

    # 出力（フォーマットを保持）
    try:
        with output_path.open('w', encoding='utf-8') as f:
            yaml.dump(data, f)
    except Exception as e:
        print(f"❌ Error: Failed to write YAML: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Normalized: {input_path} → {output_path}")

    # 統計情報を出力
    try:
        original_size = input_path.stat().st_size
        normalized_size = output_path.stat().st_size
        reduction = ((original_size - normalized_size) / original_size) * 100

        with input_path.open('r') as f:
            original_lines = len(f.readlines())
        with output_path.open('r') as f:
            normalized_lines = len(f.readlines())

        print(f"📊 Size: {original_size:,} → {normalized_size:,} bytes ({reduction:+.1f}%)")
        print(f"📊 Lines: {original_lines:,} → {normalized_lines:,} ({normalized_lines - original_lines:+,})")
    except:
        pass


if __name__ == '__main__':
    main()
