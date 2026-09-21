# Elsewhere - v2

PY ?= python3
N ?= 5

test:            ## run everything that needs no model
	ELSEWHERE_BACKEND=stub $(PY) -m unittest discover -s tests

world:           ## make a world in ./world (needs a reachable model)
	elsewhere init --world world

demo:            ## the whole pipeline, offline, with no model at all
	ELSEWHERE_BACKEND=stub $(PY) -m unittest tests.test_fire -v

tick:            ## live one phase now (N=3 for three)
	elsewhere tick -n $(or $(TICKS),1)

news:            ## what happened since you last looked
	elsewhere news

schedule:        ## keep the world going while you are away (launchd)
	./scripts/schedule.sh install

unschedule:      ## stop it
	./scripts/schedule.sh uninstall

schedule-status: ## is it running, and can it reach a mind
	./scripts/schedule.sh status

doctor:          ## can the configured minds be reached?
	elsewhere doctor

live:            ## serve a model on this Mac and put the fire to it
	./scripts/live.sh

eval:            ## put the fire to the model N times (N=5) and measure it
	elsewhere eval fire -n $(N)

diagnose:        ## find out why the MLX server will not start
	./scripts/diagnose.sh

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-9s %s\n", $$1, $$2}'

.PHONY: test world demo doctor live eval diagnose help tick news schedule unschedule schedule-status
