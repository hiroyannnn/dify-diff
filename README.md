# Dify DSL Diff Checker

Dify ワークフローの DSL ファイル（`.yml`）の**意味のある差分**だけを GitHub の UI で確認できるツールです。

## 🎯 特徴

✨ **超シンプル**: ローカル環境のセットアップ不要
🤖 **自動化**: PR を作成するだけで `.norm.yml` が自動生成される
👀 **GitHub UI**: 慣れた GitHub の差分 UI で直接確認
🧠 **LLM 解析**: OpenAI API で差分を意味解析し、影響度を自動判定

## 📊 どう動くの？

```
あなたがやること:
  1. chat.yml を編集
  2. コミット & PR 作成

GitHub Actions が自動で:
  3. chat.norm.yml を生成（UI メタデータを除外）
  4. PR に自動コミット
  5. LLM で差分を解析
  6. 結果を PR にコメント

あなたが確認:
  7. GitHub の "Files changed" で chat.norm.yml の差分を確認
  8. LLM の解析レポートを読む
```

## 🚀 セットアップ（3ステップ）

### 1. このリポジトリを GitHub にプッシュ

```bash
git add .
git commit -m "feat: Add Dify DSL diff checker"
git push origin main
```

### 2. OpenAI API キーを設定

GitHub リポジトリの **Settings > Secrets and variables > Actions** で追加：

- **Name**: `OPENAI_API_KEY`
- **Value**: `sk-...` （あなたの OpenAI API キー）

### 3. 完了！

これだけです。次から PR を作ると自動的に動きます。

## 💻 使い方

### 基本的な流れ

```bash
# 1. ブランチ作成
git checkout -b feature/update-workflow

# 2. Dify DSL を編集
# （Dify の UI で編集してエクスポート、または直接編集）
vim chat.yml

# 3. コミット（.yml ファイルだけでOK）
git add chat.yml
git commit -m "feat: Add new LLM node"

# 4. プッシュ & PR 作成
git push origin feature/update-workflow
# GitHub で PR を作成

# 5. 自動的に起こること:
#   - GitHub Actions が chat.norm.yml を生成
#   - PR に自動コミット
#   - LLM が差分を解析
#   - 結果を PR にコメント
```

### PR で確認すること

1. **Files changed タブ**:
   - `chat.yml`: 元のファイル（UI メタデータ含む）
   - `chat.norm.yml`: 正規化版（**これを見る！**）

2. **Conversation タブ**:
   - bot のコメントで LLM 解析結果を確認

## 📁 ファイル構成

```
.
├── .github/
│   └── workflows/
│       └── dify-diff-check.yml    # 自動化 workflow
├── scripts/
│   ├── normalize_dify.py          # 正規化スクリプト
│   └── llm_diff_analyzer.py       # LLM 解析スクリプト
├── chat.yml                        # あなたの Dify DSL
├── chat.norm.yml                   # 自動生成される（Git 管理対象）
├── requirements.txt                # Python 依存関係
├── Makefile                        # ローカルテスト用
├── DIFFY_DIFF_GUIDE.md            # 詳細ガイド
└── README.md                       # このファイル
```

## 🔍 何が除外されるの？

### 除外されるフィールド（UI メタデータ）

| フィールド | 説明 |
|-----------|------|
| `position.x/y` | ノードの canvas 上の座標 |
| `positionAbsolute.x/y` | 絶対座標 |
| `width` / `height` | ノードのサイズ |
| `selected` | ノードの選択状態 |
| `zIndex` | 表示順序 |
| `viewport.x/y/zoom` | canvas の表示位置・ズーム |
| `sourcePosition` / `targetPosition` | エッジの接続位置 |

### 検知されるフィールド（処理に影響）

| フィールド | 説明 |
|-----------|------|
| `nodes[].data.model.*` | AI モデル設定 |
| `nodes[].data.prompt_template` | プロンプト内容 |
| `nodes[].data.completion_params` | temperature などのパラメータ |
| `edges[]` の追加・削除 | ワークフローの接続構造 |
| `features.*.enabled` | 機能の ON/OFF |
| `variables` / `environment_variables` | 変数定義 |

## 📝 PR での表示例

### Bot のコメント（ステップ1）

```markdown
## 🔄 Dify DSL 正規化完了

✅ 正規化ファイル（`.norm.yml`）を自動生成しました。

### 📊 差分の確認方法

1. **Files changed** タブを開く
2. `.norm.yml` ファイルを探す
3. **UI メタデータ（position, selected など）が除外された差分**を確認できます

⏳ **LLM による意味解析を実行中...**
```

### Bot のコメント（ステップ2）

```markdown
## 🔍 Dify DSL 差分解析レポート

### 🔴 総合影響度: HIGH

**要約**: 新しい LLM ノード（gemini-2.5-pro）が追加されました

---

### 📋 変更一覧

#### 1. ➕ ADDED - graph

- **影響度**: 🔴 HIGH
- **説明**: LLM 2 ノード（gemini-2.5-pro）がワークフローに追加されました
- **アクション**: 要レビュー

---

### 💡 推奨アクション

新しいモデルの追加により、処理フローが変更されています。以下を確認してください：
- プロンプトの内容は適切か
- モデルのパラメータ設定は正しいか
- コスト影響を検討したか
```

## 🛠️ ローカルでのテスト（オプション）

開発者向け：Actions を動かす前にローカルでテストできます。

```bash
# 依存関係をインストール
make install

# 正規化をテスト
make test-normalize

# LLM 解析をテスト（要: OPENAI_API_KEY）
export OPENAI_API_KEY="sk-..."
make test-llm

# すべての .yml を正規化
make normalize
```

## ⚙️ カスタマイズ

### 無視するフィールドを追加

`scripts/normalize_dify.py` の `DROP_FIELDS` を編集：

```python
DROP_FIELDS = {
    'position', 'positionAbsolute', 'width', 'height',
    'selected', 'zIndex', 'viewport',
    'sourcePosition', 'targetPosition',
    # 追加
    'your_custom_field'
}
```

### LLM モデルを変更

`.github/workflows/dify-diff-check.yml` の `LLM_MODEL` を変更：

```yaml
env:
  LLM_MODEL: gpt-4o  # または gpt-4-turbo など
```

## 💰 コスト試算

| モデル | 月間100回 PR | 月間1000回 PR |
|--------|-------------|--------------|
| gpt-4o-mini | 約4円 | 約40円 |
| gpt-4o | 約90円 | 約900円 |

※ 1回あたり500トークン（入力）+ 300トークン（出力）と仮定

## 🐛 トラブルシューティング

### Q: `.norm.yml` が生成されない

**A**: 以下を確認してください：
- `.yml` ファイルを変更しましたか？（`.norm.yml` は自動生成されるため、手動で作る必要はありません）
- Actions タブでワークフローが実行されていますか？
- ワークフローのログにエラーが出ていませんか？

### Q: LLM 解析が失敗する

**A**: 以下を確認してください：
- `OPENAI_API_KEY` が正しく設定されていますか？
- OpenAI API の使用量制限に達していませんか？
- [OpenAI Status](https://status.openai.com/) でサービス障害が発生していませんか？

### Q: bot のコミットが多すぎる

**A**: `.norm.yml` の生成は PR ごとに 1回だけ実行されます。もし頻繁に実行される場合は、コミットメッセージに `[skip ci]` が含まれているか確認してください。

## 🎨 なぜこの方式？

### 他のアプローチとの比較

| アプローチ | 長所 | 短所 |
|-----------|------|------|
| **pre-commit hook** | ローカルで完結 | 環境構築が必要、導入の手間 |
| **Actions で一時生成** | 環境構築不要 | GitHub UI で差分を見られない |
| **Actions で自動コミット** ⭐ | 環境構築不要、GitHub UI で確認可能 | `.norm.yml` が Git 履歴に残る |

この実装は **Actions で自動コミット** を採用しています：

✅ ローカル環境のセットアップ不要
✅ GitHub の差分 UI で直接確認
✅ チーム全員が同じ方法で確認できる
✅ `.norm.yml` をレビューの一部として扱える

## 📚 詳細ドキュメント

- [DIFFY_DIFF_GUIDE.md](./DIFFY_DIFF_GUIDE.md) - 設計思想と4つのアプローチの比較

## 🤝 コントリビューション

改善提案や不具合報告は Issue または PR でお願いします！

## 📄 ライセンス

MIT License

---

**Happy Dify Workflow Development! 🚀**
