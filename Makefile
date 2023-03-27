.PHONY: lint lint-shell lint-plugin lint-python tests tests-python run
lint-shell:
	docker compose run --rm lint-shell

lint-plugin:
	docker compose run --rm lint-plugin 

lint-python:
	docker compose run --rm lint-python

lint: lint-shell lint-plugin lint-python

tests-python:
	docker compose run --rm tests-python

tests: tests-python

run: check_BUILDKITE_PIPELINE_NAME check_BUILDKITE_COMMIT .venv
	sh -c ". .venv/bin/activate && python3 pipeline/pipeline.py"

.venv:
	python3 -m venv .venv
	sh -c ". .venv/bin/activate && python3 -m pip install -r requirements.txt"
