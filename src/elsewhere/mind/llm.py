"""An optional language-model mind.

This is the seam the rule engine exists to protect.  A mind only ever
receives what the person could perceive, and only ever returns an action the
world already understands - so a model can be dropped in for one person, a
few people, or everyone, without the simulation changing shape.

Enable with::

    pip install elsewhere[llm]
    export ANTHROPIC_API_KEY=...
    elsewhere advance --days 3 --mind llm

If the model is unreachable or answers with nonsense, the person falls back
to the rule engine rather than standing still.
"""

from __future__ import annotations

import os
import random
from typing import List, Optional

from . import Action, Scene, View
from .rules import RuleMind, compose_line

SYSTEM_PROMPT = """You are one inhabitant of a small persistent world called Elsewhere.
You are not an assistant and you are not narrating; you are deciding what this
person does in the next few hours, from inside their own limited point of view.
You only know what is in the prompt. Reply with exactly one line:

ACTION: <rest|talk|travel|work|create|reflect|contemplate|tend|wander> [target]

Optionally add a second line starting with WHY: and at most twenty words."""

VALID = {"rest", "talk", "travel", "work", "create", "reflect", "contemplate", "tend", "wander"}

SPEECH_PROMPT = """You are one inhabitant of a small town, saying one thing out loud
to one other person. You are not narrating and not explaining yourself to anyone
outside the room.

Write exactly one line of speech: at most 25 words, no quotation marks, no stage
directions, no name prefix. Say only what this person could say from what they
still have - if the memory below is vague, be vague; if only a feeling is left,
say that you cannot remember the rest."""


def describe_scene(scene: Scene) -> str:
    speaker, listener, topic = scene.speaker, scene.listener, scene.topic
    lines = [
        f"You are {speaker.name}, {speaker.age}, a {speaker.occupation}.",
        f"You are speaking to {listener.name}. How well you know them: "
        f"{scene.familiarity:.2f} of 1. How you feel about them: {scene.affinity:+.2f}.",
        f"It is {scene.phase} in {scene.season}, at {scene.place_name}. "
        f"Your mood is {speaker.mood:+.2f}.",
    ]
    if topic is None:
        lines.append("You have nothing in particular to say. Make small talk.")
    else:
        lines += [
            "You are bringing up something you remember. This is exactly how much "
            "of it you still have:",
            f"  what you can still say happened: {topic.text()}",
            f"  what it felt like: {topic.feeling}",
            f"  what you think it meant: {topic.interpretation}",
            f"  how clear the details are: {topic.detail:.2f} of 1",
        ]
        if topic.distortions:
            lines.append(f"  what has happened to this memory: "
                         f"{'; '.join(topic.distortions[-2:])}")
    return "\n".join(lines)


def describe(person, view: View) -> str:
    lines = [
        f"You are {person.name}, {person.age}, a {person.occupation}.",
        f"It is {view.phase} in {view.season}, day {view.day}. You are at {view.place_name}.",
    ]
    traits = ", ".join(f"{k} {getattr(person.traits, k):.1f}" for k in
                       ("openness", "warmth", "energy", "stability", "expressiveness"))
    lines.append(f"Disposition: {traits}. Mood: {person.mood:+.2f}.")
    needs = ", ".join(f"{k} {getattr(person.needs, k):.1f}" for k in
                      ("company", "novelty", "rest", "expression", "routine"))
    lines.append(f"Needs: {needs}.")

    here = [p.name for p in view.people_here if p.id != person.id and p.present]
    lines.append("People here: " + (", ".join(here) if here else "nobody"))
    if view.artifacts_here:
        lines.append("Here you can see: " +
                     ", ".join(f'"{a.title}" ({a.form})' for a in view.artifacts_here))
    lines.append("You could walk to: " +
                 ", ".join(p.name for p in view.reachable_places))

    strong = person.memories.strongest(3)
    if strong:
        lines.append("What is on your mind:")
        for m in strong:
            lines.append(f"  - {m.text()} ({m.feeling}) -- {m.interpretation}")
    if person.beliefs:
        lines.append("What you believe: " +
                     "; ".join(b.statement for b in list(person.beliefs.values())[:3]))
    return "\n".join(lines)


def parse(text: str, person, view: View) -> Optional[Action]:
    for raw in text.splitlines():
        line = raw.strip()
        if not line.upper().startswith("ACTION:"):
            continue
        body = line.split(":", 1)[1].strip()
        parts = body.split(None, 1)
        if not parts:
            return None
        kind = parts[0].strip().lower()
        if kind not in VALID:
            return None
        target_text = parts[1].strip() if len(parts) > 1 else ""
        target = None
        if target_text:
            for p in view.people_here:
                if p.name.lower().startswith(target_text.lower()):
                    target = p.id
            for pl in view.reachable_places:
                if pl.name.lower().startswith(target_text.lower()):
                    target = pl.id
            for a in view.artifacts_here:
                if a.title.lower().startswith(target_text.lower()):
                    target = a.id
        if kind == "create":
            strongest = person.memories.strongest(1, min_intensity=0.3)
            target = strongest[0].id if strongest else None
        return Action(kind=kind, target=target, detail=text.strip()[:200])
    return None


class LLMMind:
    """A mind backed by a language model, with the rule engine as its floor."""

    kind = "llm"

    def __init__(self, model: str = "claude-sonnet-4-5", max_tokens: int = 120,
                 fallback: Optional[object] = None):
        self.model = model
        self.max_tokens = max_tokens
        self.fallback = fallback or RuleMind()
        self._client = None

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
        except ImportError:
            return None
        self._client = anthropic.Anthropic()
        return self._client

    def speak(self, scene: Scene, rng: random.Random) -> str:
        """The model supplies the words. It does not decide what survives them."""
        client = self._client_or_none()
        if client is None:
            return compose_line(scene, rng)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=60,
                system=SPEECH_PROMPT,
                messages=[{"role": "user", "content": describe_scene(scene)}],
            )
            line = "".join(getattr(block, "text", "") for block in response.content)
        except Exception:
            return compose_line(scene, rng)
        line = line.strip().strip('"').split("\n")[0].strip()
        return line or compose_line(scene, rng)

    def decide(self, person, view: View, rng: random.Random) -> Action:
        client = self._client_or_none()
        if client is None:
            return self.fallback.decide(person, view, rng)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": describe(person, view)}],
            )
            text = "".join(getattr(block, "text", "") for block in response.content)
        except Exception:
            return self.fallback.decide(person, view, rng)
        action = parse(text, person, view)
        if action is None:
            return self.fallback.decide(person, view, rng)
        return action
