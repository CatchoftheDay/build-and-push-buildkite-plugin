.PHONY: lint lint-shell lint-plugin lint-python tests tests-python run check_% _check_% _check_variableexists_% _check_variablenowhitespace_%
lint-shell:
	docker run --rm -v "$(shell pwd)":/plugin koalaman/shellcheck -x /plugin/hooks/command

lint-plugin:
	docker run --rm -v "$(shell pwd)":/plugin buildkite/plugin-linter --id "ssh://git@github.com/CatchoftheDay/build-and-push-buildkite-plugin.git"

lint-python: .venv
	sh -c ". .venv/bin/activate && python3 -m pip install -r requirements.dev.txt"
	sh -c ". .venv/bin/activate && python3 -m pylint pipeline/pipeline.py --ignore-long-lines \".*\""

lint: lint-shell lint-plugin lint-python

tests-python: .venv
	sh -c ". .venv/bin/activate && python3 -m unittest discover -s pipeline"

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
