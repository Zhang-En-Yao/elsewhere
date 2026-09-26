# Elsewhere - v2

PY ?= python3

test: typecheck  ## run everything that needs no model
	$(PY) -m unittest discover -s tests

typecheck:       ## the mistakes a test cannot reach (pip install -e ".[dev]")
	@if $(PY) -c "import mypy" 2>/dev/null; then \
	    $(PY) -m mypy; \
	else \
	    echo "  mypy not installed, skipping: pip install -e \".[dev]\""; \
	fi

world:           ## make a world in ./world (needs a reachable model)
	elsewhere --world world initialize

watch:           ## sit with the world in a window; reads only
	elsewhere watch

tick:            ## live one step now (TICKS=3 for three)
	elsewhere tick -n $(or $(TICKS),1)

news:            ## what happened since you last looked
	elsewhere news

schedule:        ## keep the world going while you are away (launchd)
	./scripts/schedule.sh install

unschedule:      ## stop it
	./scripts/schedule.sh uninstall

end:             ## end the world for good, and stop the schedule
	elsewhere --world world end
	./scripts/schedule.sh uninstall

schedule-status: ## is it running, and can it reach a mind
	./scripts/schedule.sh status

doctor:          ## can the configured minds be reached?
	elsewhere doctor

live:            ## put a model on this Mac (MLX) and check every call site can reach it
	./scripts/live.sh

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-9s %s\n", $$1, $$2}'

.PHONY: test typecheck world doctor live help watch tick news schedule \
        unschedule schedule-status end
