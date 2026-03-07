.PHONY: test eval-smoke eval-nightly eval-compare lint

# Run all unit tests
test:
	uv run --extra dev python -m pytest tests/ -v

# Smoke eval — mock LLM, no external keys, CI-safe
eval-smoke:
	uv run --extra dev python -m eval.smoke_runner smoke \
		--cases eval/cases \
		--artifacts eval/artifacts-smoke

# Nightly live eval — requires AC_EVAL_TOKEN (skips gracefully if missing)
eval-nightly:
	uv run --extra dev python -m eval.smoke_runner nightly \
		--cases eval/cases \
		--artifacts eval/artifacts-nightly

# Compare current run against baseline (set BASELINE / CURRENT paths)
# Usage: make eval-compare BASELINE=eval/artifacts-baseline/report.json CURRENT=eval/artifacts/report.json
BASELINE ?= eval/artifacts-baseline/report.json
CURRENT  ?= eval/artifacts/report.json
eval-compare:
	uv run python -m eval.compare \
		--baseline $(BASELINE) \
		--current $(CURRENT) \
		--max-pass-rate-drop 0.05

# Lint
lint:
	uv run --extra dev ruff check src/ eval/ tests/
