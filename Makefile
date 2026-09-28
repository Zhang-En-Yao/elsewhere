# Elsewhere

# The project's venv when there is one, so nothing depends on it being activated.
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELSEWHERE ?= $(if $(wildcard .venv/bin/elsewhere),.venv/bin/elsewhere,elsewhere)

test: typecheck  ## run everything that needs no model
	$(PY) -m unittest discover -s tests

typecheck:       ## the mistakes a test cannot reach (pip install -e ".[dev]")
	@if $(PY) -c "import mypy" 2>/dev/null; then \
	    $(PY) -m mypy; \
	else \
	    echo "  mypy not installed, skipping: pip install -e \".[dev]\""; \
	fi

world:           ## make a world in ./world and keep it going (launchd)
	$(ELSEWHERE) --world world initialize
	./scripts/schedule.sh install

watch:           ## sit with the world in a window; reads only
	$(ELSEWHERE) watch

tick:            ## live one step now (TICKS=3 for three)
	$(ELSEWHERE) tick -n $(or $(TICKS),1)

news:            ## what happened since you last looked
	$(ELSEWHERE) news

schedule:        ## keep the world going while you are away (launchd)
	./scripts/schedule.sh install

unschedule:      ## stop it
	./scripts/schedule.sh uninstall

end:             ## end the world for good, and stop the schedule
	$(ELSEWHERE) --world world end
	./scripts/schedule.sh uninstall

status:          ## is the schedule installed, and when did it last run
	./scripts/schedule.sh status

doctor:          ## can the configured minds be reached?
	$(ELSEWHERE) doctor

live:            ## put a model on this Mac (MLX) and check every call site can reach it
	./scripts/live.sh

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-9s %s\n", $$1, $$2}'

.PHONY: test typecheck world doctor live help watch tick news schedule \
        unschedule status end
