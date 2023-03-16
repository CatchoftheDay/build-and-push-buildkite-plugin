.PHONY: lint lint-shell lint-plugin lint-python tests tests-python run check_% _check_% _check_variableexists_% _check_variablenowhitespace_%
lint-shell:
	docker-compose run --rm lint-shell

lint-plugin:
	docker-compose run --rm lint-plugin 

lint-python:
	docker-compose run --rm lint-python

lint: lint-shell lint-plugin lint-python

tests-python:
	docker-compose run --rm tests-python

tests: tests-python

run: check_BUILDKITE_PIPELINE_NAME check_BUILDKITE_COMMIT .venv
	sh -c ". .venv/bin/activate && python3 pipeline/pipeline.py"

.venv:
	python3 -m venv .venv
	sh -c ". .venv/bin/activate && python3 -m pip install -r requirements.txt"

check_%: # Checks a variable (that it exists and has not leading or trailing whitespace)
	@$(MAKE) _check_variableexists_$(*)
	@$(MAKE) _check_variablenowhitespace_$(*)

_check_variableexists_%: # Checks given variable is not empty
	@[[ "$($(*))" != "" ]] || (echo "ERROR: You must specify $(*)" && exit 1)

_check_variablenowhitespace_%: # Checks given variable for leading or trailing whitespace. Fails for multi-line string.
	@[[ "$($(*))" == $(strip $($(*))) ]] || (echo "ERROR: $(*) contains leading or trailing whitespace" && echo "|$($(*))|" exit 2)
