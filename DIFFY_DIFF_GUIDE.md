# Dify DSL差分を「ノイズなし」で見るためのやさしい手順書

初心者向けに、Difyの DSL (例: `chat.yml`) をきれいに比較する方法を段階的にまとめました。ポイントは「機械でノイズを消す」→「残った本質だけを見る」の二段構えです。

---

## ゴール
- エクスポートした DSL の **位置情報や自動IDの揺れ** を消す
- **本質的な差分だけ** を検知し、レビュー負荷を下げる
- 機械で潰せない残差は **LLM にラベル付け** させて優先度づけ

---

## クイックスタート（最短ルート）
1. 依存インストール  
   - `pip install ruamel.yaml`  
   - `brew install yq dyff`（mac の例。yq は mikefarah/yq 系）
2. エクスポート  
   - `dify export app > chat.yml`
3. 正規化（ノイズ削減）  
   - `python scripts/normalize_dify.py chat.yml chat.norm.yml`
4. 差分を見る  
   - `git diff --no-index chat.prev.norm.yml chat.norm.yml`  
   - あるいは `dyff between chat.prev.norm.yml chat.norm.yml`
5. LLM で残差を要約（任意）  
   - `diff.txt` を LLM に渡し、「無視リストは説明不要、要注視のみ impact/area/summary/action で JSON 出力」を指示

これで、見たい差分だけが残るはずです。

---

## なぜノイズが出るのか？
- Dify のノードには **位置 (position, positionAbsolute)**、**サイズ (width/height)**、**UI 状態 (selected)** が含まれ、エクスポート時に揺れます。
- **自動採番 ID**（ノード/エッジ id）が毎回変わることがあります。
- 並び順に意味がない配列（例: allowed_file_extensions）がソートされず出力されることがあります。

---

## ノイズを消す基本戦略
- **正規化**: キーをソートし、整形して表面的な差分を消す（`yq -P --sortKeys`）。  
- **フィールド削除**: 位置・サイズ・UI 状態などレビュー不要なフィールドを削除。  
- **配列ソート**: 順序に意味がない配列をソート。  
- **安定 ID**: 自動採番 ID をタイトルやプロンプトから計算したハッシュで再発行（揺れを止める）。  
- **構造 diff ツール**: `dyff` や `jd` を使うと順序ノイズに強く、読みやすい。

---

## スクリプト雛形 `scripts/normalize_dify.py`
- 役割  
  - UI ノイズ（位置・サイズ・selected 等）の削除  
  - order-insensitive 配列のソート  
  - ノード/エッジの ID を安定ハッシュに差し替え  
  - キーをソートして決定論的な YAML を出力
- 使い方  
  - `python scripts/normalize_dify.py chat.yml chat.norm.yml`
- 依存  
  - `ruamel.yaml`
- 拡張ポイント  
  - `DROP_FIELDS`, `LIST_SORT_KEYS` に自分たちの無視リストを追記  
  - `make_stable_node_id/make_stable_edge_id` を、業務ドメインに合わせて強化  
  - 大きなグラフや独自ノード型がある場合は、意味のあるフィールドをハッシュに足す

---

## 差分の優先度ルール（例）
- **無視**: 位置・サイズ・UI 選択、固定 null/false、並び替えのみ  
- **要注視**: モデル種/temperature 等 `completion_params`、`prompt_template` テキスト、`features.*.enabled` のオン/オフ、`variables` 追加削除、`edges` 増減、`answer/context` 式変更  
- **要確認（ドメイン依存）**: `environment_variables`, アップロード制限、RAG 設定 (`retriever_resource`)

---

## LLM を使うなら
- 入力: 正規化後の `diff.txt` を小さめの塊で渡す  
- プロンプト例:  
  - 「無視リスト項目は説明不要。要注視リストの差分を“動作変化/リスク”観点で要約し、曖昧は“要確認”。JSON で `{impact: high|medium|low, area: model|prompt|features|graph, summary: "...", action: "要レビュー|無視可"}`」  
- 出力利用: Slack/GitHub PR コメントで自動通知

---

## CI に組み込むときの流れ
1. `dify export app > chat.yml`
2. `python scripts/normalize_dify.py chat.yml chat.norm.yml`
3. `git diff --no-index chat.prev.norm.yml chat.norm.yml > diff.txt`
4. `dyff` で人間向け差分（任意）  
5. `diff.txt` が空なら自動で「差分なし」。そうでなければ LLM 要約を投稿。

---

## これで得られること
- レビューで見るべき差分だけが残り、揺れる UI 系フィールドは消える。  
- 自動採番 ID のブレが止まり、PR のノイズが激減。  
- LLM は残差を優先度づけする補助として使い、人間の目は「意味のある変更」だけに集中できる。  

困ったときは `scripts/normalize_dify.py` の DROP_FIELDS / LIST_SORT_KEYS / stable ID 関数をあなたの環境に合わせて調整してください。
