.PHONY: help install normalize test-normalize test-llm clean status

help: ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 依存関係をインストール
	pip install -r requirements.txt
	@echo "✅ Dependencies installed!"
	@echo ""
	@echo "📝 Next steps:"
	@echo "  1. Set OPENAI_API_KEY in GitHub Secrets"
	@echo "  2. Edit chat.yml and commit"
	@echo "  3. Create PR"
	@echo "  4. GitHub Actions will automatically generate .norm.yml files! ✨"

normalize: ## すべての .yml ファイルを正規化（ローカルテスト用）
	@echo "🔄 Normalizing all Dify DSL files..."
	@for file in *.yml; do \
		if [ -f "$$file" ] && [ "$$file" != "*.norm.yml" ] && ! echo "$$file" | grep -q '\.norm\.yml$$'; then \
			norm_file="$${file%.yml}.norm.yml"; \
			echo "  📄 $$file → $$norm_file"; \
			python scripts/normalize_dify.py "$$file" "$$norm_file"; \
		fi \
	done
	@echo "✅ Normalization complete!"

test-normalize: ## 正規化スクリプトのテスト
	@echo "🧪 Testing normalization..."
	@python scripts/normalize_dify.py chat.yml /tmp/chat.norm.yml
	@echo "✅ Test passed! Output: /tmp/chat.norm.yml"

test-llm: ## LLM 解析のテスト（要: OPENAI_API_KEY）
	@echo "🧪 Testing LLM analysis..."
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "❌ Error: OPENAI_API_KEY is not set"; \
		echo "   Run: export OPENAI_API_KEY='sk-...'"; \
		exit 1; \
	fi
	@git diff chat.yml > /tmp/test_diff.txt 2>/dev/null || echo "--- a/test\n+++ b/test\n+test" > /tmp/test_diff.txt
	@python scripts/llm_diff_analyzer.py /tmp/test_diff.txt
	@echo "✅ Test passed!"

clean: ## 生成されたファイルをクリーンアップ
	@echo "🧹 Cleaning up..."
	@rm -f *.norm.yml
	@rm -rf diffs/
	@echo "✅ Cleanup complete!"

status: ## Git status と正規化ファイルの状態を表示
	@echo "📋 Git Status:"
	@git status --short
	@echo ""
	@echo "📋 Normalized files:"
	@ls -lh *.norm.yml 2>/dev/null || echo "  (no .norm.yml files found)"
