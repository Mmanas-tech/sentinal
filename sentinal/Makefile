.PHONY: dev test

dev:
	npm install --no-audit --no-fund
	npm run build
	python -m uvicorn api.main:app --reload --app-dir sentinal

test:
	python -m pytest -q sentinal/tests
