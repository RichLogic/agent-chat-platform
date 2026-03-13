.PHONY: test eval-smoke eval-nightly eval-compare eval-regression eval-regression-smoke eval-regression-live lint

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


# Interview-oriented smoke regression (mock LLM, stable local sanity check)
# Usage: make eval-regression-smoke CASE_FILE=interview_reliability_smoke.yaml
CASE_FILE ?= interview_reliability_smoke.yaml
eval-regression: eval-regression-smoke

eval-regression-smoke:
	uv run --extra dev python -m eval.regression_runner \
		--mode smoke \
		--cases eval/cases \
		--case-file $(CASE_FILE) \
		--artifacts eval/artifacts-interview

# Interview-oriented live regression (real server / real auth)
# Usage: make eval-regression-live EVAL_TOKEN=... EVAL_BASE_URL=http://localhost:8301 LIVE_CASE_FILE=interview_reliability.yaml
LIVE_CASE_FILE ?= interview_reliability.yaml
EVAL_BASE_URL ?= http://localhost:8301
EVAL_TOKEN ?= $(AC_EVAL_TOKEN)
eval-regression-live:
	uv run --extra dev python -m eval.regression_runner \
		--mode live \
		--cases eval/cases \
		--case-file $(LIVE_CASE_FILE) \
		--artifacts eval/artifacts-interview-live \
		--base-url $(EVAL_BASE_URL) \
		--token $(EVAL_TOKEN)

# Lint
lint:
	uv run --extra dev ruff check src/ eval/ tests/
