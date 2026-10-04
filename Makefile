# Elsewhere

# The project's venv when there is one, so nothing depends on it being activated.
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELSEWHERE ?= $(if $(wildcard .venv/bin/elsewhere),.venv/bin/elsewhere,elsewhere)

# For make configure: MODEL is required, the rest optional. ENDPOINT left empty is
# the backend's own default; EMBEDDER left empty leaves the embedder as it is, and
# EMBEDDER_ENDPOINT left empty is ENDPOINT.
BACKEND ?= openai

test: typecheck  ## run everything that needs no model
	$(PY) -m unittest discover -s tests

typecheck:       ## the mistakes a test cannot reach (pip install -e ".[dev]")
	@if $(PY) -c "import mypy" 2>/dev/null; then \
	    $(PY) -m mypy; \
	else \
	    echo "  mypy not installed, skipping: pip install -e \".[dev]\""; \
	fi

format:          ## rewrite the code the way black lays it out (pip install -e ".[dev]")
	$(PY) -m black src tests scripts

lint:            ## check the layout without changing anything
	$(PY) -m black --check --diff src tests scripts

initialize:      ## make a world in ./world
	$(ELSEWHERE) --world world initialize

configure:       ## point the minds (and EMBEDDER, if given) at MODEL on BACKEND at ENDPOINT
	$(if $(MODEL),,$(error MODEL is required: make configure MODEL=<id> ENDPOINT=<url>))
	$(ELSEWHERE) --world world configure --backend $(BACKEND) --model $(MODEL) \
	  $(if $(ENDPOINT),--endpoint $(ENDPOINT)) $(foreach site,$(CALLS),--call $(site))
	$(if $(EMBEDDER),$(ELSEWHERE) --world world configure --backend $(BACKEND) --model $(EMBEDDER) \
	  $(if $(or $(EMBEDDER_ENDPOINT),$(ENDPOINT)),--endpoint $(or $(EMBEDDER_ENDPOINT),$(ENDPOINT))) --call embed)

world: initialize ## make a world in ./world and keep it going (launchd)
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

logo:            ## draw docs/logo.jpg again for the window (needs Pillow)
	$(PY) scripts/logo.py

help:
	@echo "Start, without a served model"
	@echo "  make live               Install MLX, fetch MODEL and EMBEDDER, write them into ./world"
	@echo "  make world              Initialize ./world, then schedule it"
	@echo ""
	@echo "Start, with a served model"
	@echo "  make initialize         Make ./world; its minds stay on MLX until configured"
	@echo "  make configure MODEL=<id> ENDPOINT=http://localhost:8080/v1 \\"
	@echo "                 EMBEDDER=<id> EMBEDDER_ENDPOINT=http://localhost:8081/v1"
	@echo "                          Point every mind at MODEL and the embedder at EMBEDDER, in one go;"
	@echo "                          EMBEDDER_ENDPOINT only when the embedder is served on another port"
	@echo "  make doctor             Every mind should answer ok"
	@echo "  make schedule"
	@echo "                          <id> is one the server lists: curl <endpoint>/models"
	@echo "                          Configure before scheduling: the schedule lives a step the moment it is"
	@echo "                          installed, and an unconfigured world reaches for MLX. So not make world,"
	@echo "                          which schedules before you configure, and not make live, which installs"
	@echo "                          MLX and points the world back at it"
	@echo "                          An embedder whose server has no /v1/embeddings leaves retrieval on BM25"
	@echo "                          alone; it still works"
	@echo "                          A server that needs a key reads it from ELSEWHERE_OPENAI_KEY"
	@echo ""
	@echo "Configure, any time after"
	@echo "  make configure MODEL=<id> CALLS=\"speak consolidate\""
	@echo "                          Only these call sites (act, speak, consolidate, stir); default every mind"
	@echo "  make configure MODEL=<id> BACKEND=mlx"
	@echo "                          Back to a model run in this process"
	@echo ""
	@echo "Run"
	@echo "  make tick               Live one step now; TICKS=3 for three"
	@echo "  make schedule           Keep the world going while you are away (launchd)"
	@echo "  make unschedule         Stop the schedule; the world waits where it is"
	@echo ""
	@echo "Inspect"
	@echo "  make watch              Sit with the world in a window; reads only"
	@echo "  make news               What happened since you last looked"
	@echo "  make status             Is the schedule installed, and when did it last run"
	@echo "  make doctor             Can the configured minds be reached? Loads the model, so it takes a while"
	@echo ""
	@echo "Clear"
	@echo "  make end                End the world for good, and stop the schedule; what happened stays readable"
	@echo ""
	@echo "Development"
	@echo "  make test               Typecheck, then everything that needs no model (a stub answers)"
	@echo "  make typecheck          The mistakes a test cannot reach (pip install -e \".[dev]\")"
	@echo "  make format             Rewrite the code the way black lays it out"
	@echo "  make lint               Check the layout without changing anything"
	@echo "  make logo               Draw docs/logo.jpg again for the window (needs Pillow)"
	@echo ""
	@echo "Settings (override on the command line, e.g. make tick TICKS=3)"
	@echo "  PY                 = $(PY)"
	@echo "  ELSEWHERE          = $(ELSEWHERE)"
	@echo "  TICKS              = $(or $(TICKS),1)"
	@echo "  BACKEND            = $(BACKEND)"
	@echo "  MODEL              = $(MODEL)"
	@echo "  EMBEDDER           = $(EMBEDDER)"
	@echo "  ENDPOINT           = $(or $(ENDPOINT),the backend's own default)"
	@echo "  EMBEDDER_ENDPOINT  = $(or $(EMBEDDER_ENDPOINT),ENDPOINT)"
	@echo "  CALLS              = $(or $(CALLS),every mind)"
	@echo "                       make live reads MODEL and EMBEDDER too; its defaults are in scripts/live.sh"
	@echo "  CHECK_EVERY, MAX   read by make schedule; defaults in scripts/schedule.sh"

.PHONY: test typecheck format lint initialize configure world doctor live logo help watch tick news schedule \
        unschedule status end
