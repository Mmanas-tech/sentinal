.PHONY: dev test

dev:
	npm --prefix sentinal/web install --no-audit --no-fund
	npm --prefix sentinal/web run build
	python -m uvicorn api.main:app --reload --reload-dir sentinal --app-dir sentinal

test:
	$(MAKE) -f sentinal/Makefile test
