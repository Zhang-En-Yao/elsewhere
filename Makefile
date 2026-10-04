# Elsewhere

# The project's venv when there is one, so nothing depends on it being activated.
PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ELSEWHERE ?= $(if $(wildcard .venv/bin/elsewhere),.venv/bin/elsewhere,elsewhere)

# Styling: only on a terminal, never when NO_COLOR is set (https://no-color.org).
# Recipes are silent; each prints one heading of its own and leaves the rest to the command.
.SILENT:
COLOR := $(if $(NO_COLOR),,$(shell [ -t 2 ] && echo yes))
BOLD  := $(if $(COLOR),$(shell printf '\033[1m'))
DIM   := $(if $(COLOR),$(shell printf '\033[2m'))
CYAN  := $(if $(COLOR),$(shell printf '\033[36m'))
RESET := $(if $(COLOR),$(shell printf '\033[0m'))
heading = printf '$(CYAN)▸$(RESET) $(BOLD)%s$(RESET)\n' '$(1)'
section = printf '\n$(BOLD)%s$(RESET)\n' '$(1)'
entry   = printf '  $(CYAN)%-26s$(RESET) %s\n' '$(1)' '$(2)'
note    = printf '  $(DIM)%s$(RESET)\n' '$(1)'

# For make configure: MODEL is required, the rest optional. ENDPOINT left empty is
# the backend's own default; EMBEDDER left empty leaves the embedder as it is, and
# EMBEDDER_ENDPOINT left empty is ENDPOINT.
BACKEND ?= openai

test: typecheck  ## run everything that needs no model
	@$(call heading,Typecheck, then run the suite)
	$(PY) -m unittest discover -s tests

typecheck:       ## the mistakes a test cannot reach (pip install -e ".[dev]")
	@$(call heading,Typechecking)
	@if $(PY) -c "import mypy" 2>/dev/null; then \
	    $(PY) -m mypy; \
	else \
	    echo "  mypy not installed, skipping: pip install -e \".[dev]\""; \
	fi

format:          ## rewrite the code the way black lays it out (pip install -e ".[dev]")
	@$(call heading,Formatting)
	$(PY) -m black src tests scripts

lint:            ## check the layout without changing anything
	@$(call heading,Checking layout)
	$(PY) -m black --check --diff src tests scripts

initialize:      ## make a world in ./world
	@$(call heading,Initializing ./world)
	$(ELSEWHERE) --world world initialize

configure:       ## point the minds (and EMBEDDER, if given) at MODEL on BACKEND at ENDPOINT
	@$(call heading,Configuring the minds)
	$(if $(MODEL),,$(error MODEL is required: make configure MODEL=<id> ENDPOINT=<url>))
	$(ELSEWHERE) --world world configure --backend $(BACKEND) --model $(MODEL) \
	  $(if $(ENDPOINT),--endpoint $(ENDPOINT)) $(foreach site,$(CALLS),--call $(site))
	$(if $(EMBEDDER),$(ELSEWHERE) --world world configure --backend $(BACKEND) --model $(EMBEDDER) \
	  $(if $(or $(EMBEDDER_ENDPOINT),$(ENDPOINT)),--endpoint $(or $(EMBEDDER_ENDPOINT),$(ENDPOINT))) --call embed)

world: initialize ## make a world in ./world and keep it going (launchd)
	@$(call heading,Scheduling ./world)
	./scripts/schedule.sh install

watch:           ## sit with the world in a window; reads only
	@$(call heading,Watching the world)
	$(ELSEWHERE) watch

tick:            ## live one step now (TICKS=3 for three)
	@$(call heading,Living a step)
	$(ELSEWHERE) tick -n $(or $(TICKS),1)

news:            ## what happened since you last looked
	@$(call heading,News)
	$(ELSEWHERE) news

schedule:        ## keep the world going while you are away (launchd)
	@$(call heading,Scheduling ./world)
	./scripts/schedule.sh install

unschedule:      ## stop it
	@$(call heading,Stopping the schedule)
	./scripts/schedule.sh uninstall

end:             ## end the world for good, and stop the schedule
	@$(call heading,Ending the world)
	$(ELSEWHERE) --world world end
	./scripts/schedule.sh uninstall

clean:           ## delete ./world and the schedule's log (no undo; make end first to stop the schedule)
	@$(call heading,Deleting ./world and the log)
	rm -rf world .elsewhere/continue.log

status:          ## is the schedule installed, and when did it last run
	@$(call heading,Schedule status)
	./scripts/schedule.sh status

doctor:          ## can the configured minds be reached?
	@$(call heading,Checking the minds)
	$(ELSEWHERE) doctor

live:            ## put a model on this Mac (MLX) and check every call site can reach it
	@$(call heading,Putting a model on this Mac)
	./scripts/live.sh

logo:            ## draw docs/logo.jpg again for the window (needs Pillow)
	@$(call heading,Drawing the logo)
	$(PY) scripts/logo.py

help:
	@printf '$(BOLD)Elsewhere$(RESET) $(DIM)- a small town of beings that live on their own clock$(RESET)\n'
	@$(call section,Start - without a served model)
	@$(call entry,make live,Install MLX and fetch MODEL and EMBEDDER; write them into ./world)
	@$(call entry,make world,Initialize ./world then schedule it)
	@$(call section,Start - with a served model)
	@$(call entry,make initialize,Make ./world; its minds stay on MLX until configured)
	@$(call entry,make configure MODEL=<id>,Point every mind at MODEL; add ENDPOINT=<url>)
	@$(call note,Add EMBEDDER=<id> for the embedder; EMBEDDER_ENDPOINT only if it is on another port)
	@$(call note,<id> is one the server lists: curl <endpoint>/models)
	@$(call note,A server that needs a key reads it from ELSEWHERE_OPENAI_KEY)
	@$(call note,An embedder with no /v1/embeddings leaves retrieval on BM25 alone; it still works)
	@$(call entry,make doctor,Every mind should answer ok)
	@$(call entry,make schedule,Keep the world going while you are away)
	@$(call note,Configure before scheduling: an installed schedule lives a step at once and an)
	@$(call note,unconfigured world reaches for MLX. So not make world - it schedules first -)
	@$(call note,and not make live - it points the world back at MLX)
	@$(call section,Configure - any time after)
	@$(call entry,make configure CALLS=...,Only these call sites - act speak consolidate stir; default every mind)
	@$(call note,make configure MODEL=<id> CALLS="speak consolidate")
	@$(call entry,make configure BACKEND=mlx,Back to a model run in this process)
	@$(call note,make configure MODEL=<id> BACKEND=mlx)
	@$(call section,Run)
	@$(call entry,make tick,Live one step now; TICKS=3 for three)
	@$(call entry,make schedule,Keep the world going while you are away - launchd)
	@$(call entry,make unschedule,Stop the schedule; the world waits where it is)
	@$(call section,Inspect)
	@$(call entry,make watch,Sit with the world in a window; reads only)
	@$(call entry,make news,What happened since you last looked)
	@$(call entry,make status,Is the schedule installed and when did it last run)
	@$(call entry,make doctor,Can the configured minds be reached - loads the model so it takes a while)
	@$(call section,Clear)
	@$(call entry,make end,End the world for good and stop the schedule; the record stays readable)
	@$(call entry,make clean,Delete ./world and the log; no undo - run make end first)
	@$(call section,Development)
	@$(call entry,make test,Typecheck then everything that needs no model - a stub answers)
	@$(call entry,make typecheck,The mistakes a test cannot reach)
	@$(call entry,make format,Rewrite the code the way black lays it out)
	@$(call entry,make lint,Check the layout without changing anything)
	@$(call entry,make logo,Draw docs/logo.jpg again for the window - needs Pillow)
	@$(call section,Settings - override on the command line e.g. make tick TICKS=3)
	@$(call entry,PY,$(PY))
	@$(call entry,ELSEWHERE,$(ELSEWHERE))
	@$(call entry,TICKS,$(or $(TICKS),1))
	@$(call entry,BACKEND,$(BACKEND))
	@$(call entry,MODEL,$(or $(MODEL),-))
	@$(call entry,EMBEDDER,$(or $(EMBEDDER),-))
	@$(call entry,ENDPOINT,$(or $(ENDPOINT),backend default))
	@$(call entry,EMBEDDER_ENDPOINT,$(or $(EMBEDDER_ENDPOINT),same as ENDPOINT))
	@$(call entry,CALLS,$(or $(CALLS),every mind))
	@$(call entry,CHECK_EVERY and MAX,Read by make schedule; defaults in scripts/schedule.sh)
	@$(call note,make live reads MODEL and EMBEDDER too; its defaults are in scripts/live.sh)
	@printf '\n'

.PHONY: test typecheck format lint initialize configure world doctor live logo help watch tick news schedule \
        unschedule status end clean
