#!/usr/bin/env bash
#
# Let the world keep going while you are away.
#
#   scripts/schedule.sh install     # start: a launchd agent checks every 30 min
#   scripts/schedule.sh status      # is it loaded, when did it last run, can it reach a mind
#   scripts/schedule.sh log         # what it has been doing
#   scripts/schedule.sh uninstall   # stop
#
# The agent runs `elsewhere continue`, which does nothing unless the wall clock
# has moved past the next thing anybody in the world said they wanted waking
# for. There is no step size: a town where everyone has settled for the night
# sleeps through it in one move, and a town in the middle of something is
# asked again in minutes. Checking every half hour means a Mac that was asleep
# catches up soon after it wakes; launchd folds the missed checks into one.
# At most MAX steps are lived per run, so a week away does not become an hour
# of model calls.
#
# The default model runs inside the job itself, through MLX, so there is no
# server to keep running: each wake loads the weights from the Hugging Face
# cache, which takes a few seconds. If it cannot, continue logs that the
# world is waiting and lives nothing.
#
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"

LABEL="com.elsewhere.continue"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
WORLD="${WORLD:-$REPO/world}"
MAX="${MAX:-8}"
CHECK_EVERY="${CHECK_EVERY:-1800}"
LOG="$REPO/.elsewhere/continue.log"

find_cli() {
  for candidate in "${VIRTUAL_ENV:-}/bin/elsewhere" "$REPO/.venv/bin/elsewhere" \
                   "$REPO/venv/bin/elsewhere" "$(command -v elsewhere 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      (cd "$(dirname "$candidate")" && echo "$PWD/$(basename "$candidate")")
      return 0
    fi
  done
  echo "Could not find the elsewhere command. Activate your venv and run: pip install -e ." >&2
  return 1
}

interpreter_of() {                # the real python behind the elsewhere script
  local shebang
  shebang="$(head -1 "$1" | sed 's/^#!//; s/ .*//')"
  python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$shebang" 2>/dev/null || echo "$shebang"
}

protected_path() {                # macOS keeps these from background jobs
  case "$1" in
    "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*|"$HOME/Library/Mobile Documents"*) return 0 ;;
    *) return 1 ;;
  esac
}

tcc_warning() {
  local cli="$1" py
  py="$(interpreter_of "$cli")"
  cat <<TXT

  !! $REPO is inside a folder macOS protects (Documents / Desktop / Downloads).
     A launchd job cannot show a permission prompt, so macOS silently refuses it
     access - the job never runs and the log stays empty. Either:

     1. Give this interpreter Full Disk Access:
          $py
        System Settings -> Privacy & Security -> Full Disk Access -> + ,
        press Cmd-Shift-G and paste the path above. Then:
          scripts/schedule.sh install

     2. Or keep the project outside those folders, e.g. ~/elsewhere, and
        install from there.

     Check with: scripts/schedule.sh status   (look for 'last exit code')
TXT
}

plist() {
  local cli="$1"
  cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$cli</string>
    <string>--world</string><string>$WORLD</string>
    <string>continue</string>
    <string>--max</string><string>$MAX</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartInterval</key><integer>$CHECK_EVERY</integer>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
XML
}

case "${1:-status}" in
  install)
    [ -f "$WORLD/world.json" ] || { echo "No world at $WORLD - run: elsewhere initialize"; exit 1; }
    cli="$(find_cli)"
    mkdir -p "$(dirname "$PLIST")" "$REPO/.elsewhere"
    plist "$cli" > "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Scheduled. $WORLD now lives at a day per day, in whatever steps"
    echo "the people in it ask for; at most $MAX per wake. Log: $LOG"
    if protected_path "$REPO"; then tcc_warning "$cli"; fi
    ;;
  uninstall)
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Unscheduled. The world stays exactly where it is until you tick it again."
    ;;
  status)
    if [ -f "$PLIST" ]; then
      echo "installed: $PLIST"
      launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null \
        | grep -E "^\s*(state|runs|last exit code)" | sed 's/^\s*/  /' || echo "  (not loaded)"
    else
      echo "not installed - run: scripts/schedule.sh install"
    fi
    cli="$(find_cli)" && "$cli" --world "$WORLD" doctor 2>/dev/null | sed -n '/act /p'
    if [ -s "$LOG" ]; then
      echo "last lines of the log:"; tail -5 "$LOG" | sed 's/^/  /'
    else
      echo "the log is empty: the job has never written anything."
      if [ -f "$PLIST" ] && protected_path "$REPO"; then tcc_warning "$cli"; fi
    fi
    ;;
  log)
    tail -n "${LINES:-60}" "$LOG"
    ;;
  plist)
    plist "$(find_cli)"
    ;;
  *)
    echo "usage: $0 install | status | log | uninstall | plist"; exit 1 ;;
esac
