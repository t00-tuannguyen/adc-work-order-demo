.PHONY: run test lint format format-check typecheck check clean eval-intake eval-risk

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

format-check:
	ruff format --check src/ tests/

# mypy is not in requirements.txt (ADR-0002); install it separately to use this target.
typecheck:
	mypy src/

check: lint format-check test

# Đánh giá trích xuất ticket trên src/seed/pdfs (gọi Gemini thật, có cache) — ADC-001 T-022
eval-intake:
	python -m eval.intake.run_eval

# Đánh giá Risk Agent soạn thông điệp escalation trên 10 tình huống (gọi OpenAI thật) — ADC-005 T-038
eval-risk:
	python -m eval.risk.run_eval

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
