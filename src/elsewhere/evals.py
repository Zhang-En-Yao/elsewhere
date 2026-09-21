"""Measuring whether four people sound like four people.

At the temperatures a mind needs to have any character, one run proves nothing
- it can pass or fail on a coin toss. So anything that changes a prompt is
judged over N runs, and against the same gate the live test uses.

The checks are deliberately crude and deliberately visible. They are not a
theory of character; they are tripwires for the specific ways a small model
has been seen to fail here:

    shared_focus   every person kept the same detail (four times "smoke")
    heavy          it weighed on everyone, including the man who keeps nothing
    copied         the trace is the engine's own vantage line handed back
    cliche         'means' is a greeting-card moral, not something anyone says
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

STOP = {"the", "and", "that", "with", "from", "into", "still", "this", "there",
        "their", "were", "was", "had", "have", "then", "they", "them", "about",
        "your", "you", "what", "when", "just", "like", "been", "over", "only"}

CLICHES = ("a reminder of", "fragility", "the importance of", "resilience",
           "a moment of", "a testament", "the power of", "transience",
           "vulnerability", "impermanence", "clarity and")

HEAVY = {"ordinary", "stays", "marks"}


def words(text: str) -> set:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower())
            if len(w) > 3 and w not in STOP}


def copied(trace: str, vantage: str) -> bool:
    """Did the mind hand back words it was given - the engine's description of
    where it stood, or one of the worked examples in the prompt?"""
    t = words(trace)
    if not t:
        return False
    sources = [vantage]
    try:
        from .prompts import PERCEIVE_EXAMPLE_TRACES
        sources += list(PERCEIVE_EXAMPLE_TRACES)
    except ImportError:
        pass
    for src in sources:
        v = words(src)
        if v and (len(t & v) >= 2 or t <= v):
            return True
    return False


_CLICHE_STEMS = re.compile(r"\b(remind\w*|fragil\w*|impermanen\w*|inevitab\w*|"
                           r"transien\w*|vulnerab\w*)\b")


def cliche(means: str) -> bool:
    """Greeting-card register. Stems, not phrases: 'another reminder of', 'a stark
    reminder of' and 'it reminds me of' are all the same move, and a phrase list
    only caught the first of them."""
    low = (means or "").lower()
    return any(c in low for c in CLICHES) or bool(_CLICHE_STEMS.search(low))


def echoes_chronicle(trace: str, event_what: str) -> bool:
    """The trace is just the history line handed back - no perception at all.
    Reported, not gated: for someone like David it may be exactly right."""
    t, e = words(trace), words(event_what)
    return bool(t) and t <= (e | {"fire", "night"})


@dataclass
class Sample:
    answers: Dict[str, dict] = field(default_factory=dict)   # person id -> raw answer

    def weight(self, pid: str) -> str:
        a = self.answers.get(pid) or {}
        w = a.get("weight")
        if w is None:
            w = "ordinary" if a.get("stuck") else "nothing"
        return w

    def kept(self) -> List[str]:
        return [pid for pid in self.answers if self.weight(pid) != "nothing"
                and (self.answers[pid].get("trace") or "").strip()]


def _focus(sample: Sample, event_words: set) -> List[set]:
    """What each kept trace is about, beyond the event itself.

    A trace that only hands the chronicle back has an empty focus. Those must
    be left out of the intersection: one empty set makes any intersection empty,
    and an earlier version of this gate passed 'no shared detail' precisely
    because people had stopped perceiving anything at all.
    """
    focus = [words(sample.answers[p]["trace"]) - event_words for p in sample.kept()]
    return [f for f in focus if f]


def shared_detail(sample: Sample, event_words: set) -> set:
    focus = _focus(sample, event_words)
    return set.intersection(*focus) if len(focus) > 1 else set()


def echoes(sample: Sample, event_what: str) -> List[str]:
    return [p for p in sample.kept()
            if echoes_chronicle(sample.answers[p].get("trace", ""), event_what)]


def gate(sample: Sample, event_words: set, event_what: str = "") -> Dict[str, bool]:
    """The acceptance test, as data. The live unittest asserts exactly this."""
    kept = sample.kept()
    heavy = [p for p in kept if sample.weight(p) in HEAVY]
    return {
        "someone kept something": len(kept) >= 2,
        "no shared detail": not shared_detail(sample, event_words),
        "not heavy on everyone": len(heavy) <= 3,
        # One person handing back the history line may be who they are. Two
        # means the model has stopped perceiving and started summarising.
        "at most one echo": len(echoes(sample, event_what)) <= 1,
    }


GATE_CHECKS = ("someone kept something", "no shared detail",
               "not heavy on everyone", "at most one echo")


def run_fire(n: int, tape_dir: Path) -> tuple:
    """Put the fire to the four of them, n times, each in a fresh world."""
    from . import agents, config as config_mod, seed
    from .backends import Transcript

    tape_dir.mkdir(parents=True, exist_ok=True)
    samples: List[Sample] = []
    world = fire = None
    for i in range(n):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "world"
            world = seed.build(root)
            config_mod.write_default(root)
            config = config_mod.load(root)
            fire = next(e for e in world.chronicle.all() if e.kind == "fire")
            world.day = fire.day
            tape = tape_dir / f"fire-{i + 1:02d}.jsonl"
            tape.write_text("", encoding="utf-8")
            agents.perceive_all(world, fire, config, Transcript(tape))
            sample = Sample()
            for line in tape.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if not row.get("ok"):
                    continue
                try:
                    sample.answers[row["about"]] = json.loads(row["raw"])
                except (json.JSONDecodeError, TypeError):
                    from .backends import extract_json
                    sample.answers[row["about"]] = extract_json(row["raw"]) or {}
            samples.append(sample)
            print(f"  run {i + 1}/{n}: " + ", ".join(
                f"{world.people[p].name} {sample.weight(p)}" for p in fire.present),
                flush=True)
    return samples, world, fire


def report(samples: List[Sample], world, fire) -> str:
    n = len(samples)
    event_words = words(fire.what) | set(fire.tags)
    vantage = (fire.data or {}).get("vantage", {})
    out: List[str] = []

    out.append(f"\nGate (what the live test asserts), over {n} runs:")
    passes = Counter()
    for s in samples:
        for check, ok in gate(s, event_words, fire.what).items():
            passes[check] += ok
    all_pass = sum(all(gate(s, event_words, fire.what).values()) for s in samples)
    for check in GATE_CHECKS:
        out.append(f"  {check:<26} {passes[check]}/{n}")
    out.append(f"  {'all of them':<26} {all_pass}/{n}")

    # 'means' is where a small model's own voice shows, so the same sentence
    # from two different people in one run is the clearest one-narrator sign.
    dup = 0
    for s in samples:
        seen = Counter((s.answers[p].get("means") or "").strip().lower().rstrip(".")
                       for p in s.kept())
        dup += sum(c for m, c in seen.items() if m and c > 1)
    kept_total = sum(len(s.kept()) for s in samples)
    out.append(f"  {'identical means, x-person':<26} {dup}/{kept_total}")

    shared = Counter()
    for s in samples:
        for w in shared_detail(s, event_words):
            shared[w] += 1
    if shared:
        out.append("  shared details: " + ", ".join(f"{w} x{c}" for w, c in shared.most_common(5)))

    out.append("\nPer person:")
    out.append(f"  {'':<7} {'weights over the runs':<36} {'copied':>7} {'cliche':>7} {'echo':>7}")
    for pid in fire.present:
        name = world.people[pid].name
        weights = Counter(s.weight(pid) for s in samples)
        wline = ", ".join(f"{w} {weights[w]}" for w in
                          ("nothing", "faint", "ordinary", "stays", "marks") if weights[w])
        cp = sum(copied((s.answers.get(pid) or {}).get("trace", ""), vantage.get(pid, ""))
                 for s in samples if pid in s.kept())
        cl = sum(cliche((s.answers.get(pid) or {}).get("means", ""))
                 for s in samples if pid in s.kept())
        ec = sum(echoes_chronicle((s.answers.get(pid) or {}).get("trace", ""), fire.what)
                 for s in samples if pid in s.kept())
        kept = sum(pid in s.kept() for s in samples)
        out.append(f"  {name:<7} {wline:<36} {cp:>3}/{kept:<3} {cl:>3}/{kept:<3} {ec:>3}/{kept:<3}")

    out.append("\nWhat they kept, last run:")
    last = samples[-1]
    for pid in fire.present:
        a = last.answers.get(pid) or {}
        name = world.people[pid].name
        if last.weight(pid) == "nothing":
            out.append(f"  {name:<7} (nothing)")
            continue
        out.append(f"  {name:<7} [{a.get('weight')}, {a.get('feeling')}] {a.get('trace', '')}")
        if a.get("means"):
            out.append(f"  {'':<7}   ~ {a['means']}")
    return "\n".join(out)


# --------------------------------------------------------------------------
# a day in the town, read back from a world's own transcripts

def day_stats(transcript_dir: Path) -> str:
    """How people spent their phases, from the act calls actually made.

    The questions are the ones the first real day raised: when someone is right
    there, does anyone say anything; and at night, does anyone go to sleep.
    """
    rows = []
    for path in sorted(Path(transcript_dir).glob("day*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("call") == "act" and row.get("ok"):
                    rows.append(row)
    if not rows:
        return "no act calls recorded yet"

    company = Counter(); alone = Counter(); night = Counter(); total = Counter()
    for row in rows:
        try:
            action = json.loads(row["raw"]).get("action", "?")
        except (json.JSONDecodeError, TypeError):
            continue
        user = row.get("user", "")
        total[action] += 1
        (alone if "Here with you: nobody." in user else company)[action] += 1
        if "It is night" in user:
            night[action] += 1

    def share(c: Counter, key: str) -> str:
        n = sum(c.values())
        return f"{c[key]}/{n}" if n else "-"

    lines = [f"{len(rows)} decisions"]
    lines.append(f"  with someone there, talked      {share(company, 'talk')}")
    lines.append(f"  at night, rested                {share(night, 'rest')}")
    lines.append(f"  went somewhere                  {share(total, 'go')}")
    lines.append("  all: " + ", ".join(f"{k} {v}" for k, v in total.most_common()))
    return "\n".join(lines)
