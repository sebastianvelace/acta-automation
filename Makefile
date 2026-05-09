PYTHON ?= .venv/bin/python

.PHONY: eval

eval:
	@echo "Limpiando tests/fixtures/llm_outputs/*.json …"
	rm -f tests/fixtures/llm_outputs/*.json
	$(PYTHON) scripts/eval_acta.py
	$(PYTHON) scripts/judge_acta.py
