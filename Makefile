# Elsewhere - v2

PY ?= python3

test:            ## run everything that needs no model
	ELSEWHERE_BACKEND=stub $(PY) -m unittest discover -s tests

world:           ## make a world in ./world (needs a reachable model)
	elsewhere init --world world

demo:            ## the whole pipeline, offline, with no model at all
	ELSEWHERE_BACKEND=stub $(PY) -m unittest tests.test_fire -v

doctor:          ## can the configured minds be reached?
	elsewhere doctor

live:            ## serve a model on this Mac and put the fire to it
	./scripts/live.sh

diagnose:        ## find out why the MLX server will not start
	./scripts/diagnose.sh

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-9s %s\n", $$1, $$2}'

.PHONY: test world demo doctor live diagnose help
