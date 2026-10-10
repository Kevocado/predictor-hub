"""F1's `pick_timing: "unknown"` must be a first-class value, not a contract failure.

**This is a live break waiting to happen, not a hypothetical.** F1_Predictor#16
changed `/facts` to report `pick_timing: "unknown"` when the session start is
absent — the honest answer, since "made before the session" is a claim about
timing relative to a start time the response did not carry. That is correct and
it shipped.

This service's `PickTiming` is `Literal["pre_kickoff", "rebuilt", "none"]`, so
`Facts(**res.json())` raises, `service._fetch` turns that into
`Upstream("f1 facts failed the contract: ValidationError")`, and the reader gets
a 502 with no summary at all. A contract that rejects the honest answer is worse
than one that omitted it: the site was fixed to be truthful and the consumer now
refuses to hear it.

Confirmed on the deployed service before changing anything: the live F1 facts
still say `pre_kickoff` (F1#16 has not redeployed), and feeding a bundle with
`"unknown"` to `Facts(**...)` raises today. When F1#16 lands, every F1 summary
becomes a 502.

The right fix is to widen the Literal and then USE the new value, because
accepting `unknown` without handling it just moves the dishonesty downstream:
the panel has a verdict with no way to say its timing is unverified.
"""
import json

import pytest

from explainer.facts import Facts, PickTiming

F1_FACTS = {
    "sport": "f1", "id": "2026-16-race", "title": "Bahrain · Race",
    "starts_at": "", "status": "upcoming", "pick_timing": "unknown",
    "pick": {"label": "Max Verstappen", "prob": 0.1479},
    "markets": [], "drivers": [], "context": {}, "players": [],
    "record": None, "result": None,
}


def test_an_unknown_pick_timing_is_accepted():
    """The break itself. Without this the F1 fix turns every summary into a 502."""
    facts = Facts(**F1_FACTS)
    assert facts.pick_timing == "unknown"


def test_unknown_is_in_the_literal_and_not_silently_widened_to_str():
    """Asserted on the Literal's own contents rather than by constructing a value.

    `Literal[..., str]` would accept `unknown` and also accept every other
    string, which is a contract that validates nothing. The point is that
    `unknown` is a NAMED, ALLOWED value, not that the check was weakened.
    """
    assert "unknown" in PickTiming.__args__, (
        f"PickTiming is {PickTiming.__args__}; `unknown` must be one of the named values"
    )
    with pytest.raises(Exception):
        Facts(**{**F1_FACTS, "pick_timing": "whenever"})


def test_the_contract_does_not_lose_its_other_values():
    """The control: widening must not become permissive."""
    for value in ("pre_kickoff", "rebuilt", "none"):
        assert value in PickTiming.__args__


def test_a_rebuilt_pick_still_cannot_carry_a_verdict():
    """The one rule the `pick_timing` Literal exists to enforce, unaffected.

    `unknown` is a new allowed value, not a hole in the old rule: a pick that
    cannot be placed in time must still be incapable of being graded.
    """
    with pytest.raises(Exception):
        Facts(**{
            **F1_FACTS,
            "pick_timing": "rebuilt",
            "result": {"pick_won": True},
        })
    # And the same for the new value: it is "not verifiable", not "verified".
    Facts(**{**F1_FACTS, "pick_timing": "unknown", "result": None})


def test_the_rendered_facts_do_not_claim_a_verified_timing():
    """Accepting the value is half the fix. The other half is not laundering it.

    The facts are the only thing the model is allowed to talk about, so a
    `pre_kickoff` in the rendered prompt teaches the model to write a timing
    claim the payload does not support. Rendered as an explicit unknown, it
    tells the model the timing is not established.
    """
    from explainer.facts import render

    text = render(Facts(**F1_FACTS))
    assert "pre_kickoff" not in text, (
        "the rendered facts state a verified timing the payload does not carry"
    )
    assert "unknown" in text.lower()


def test_a_real_bundle_still_renders_its_timing():
    """The control on the change above, on the payload shape that IS verified."""
    from explainer.facts import render

    text = render(Facts(**{**F1_FACTS, "pick_timing": "pre_kickoff"}))
    assert "pre_kickoff" in text


def test_text_that_does_not_disclose_an_unknown_timing_is_rejected():
    """The mirror of the rebuilt rule, and the reason accepting `unknown` is not
    enough on its own.

    The facts deliberately refuse to place the pick in time. A summary that
    says nothing about that reads as a normal pick, and the reader has no way to
    know the timing was never established. Silence here is the dishonesty, not
    the safety.
    """
    from conftest import rule_validate as validate

    out = {
        "verdict": "Max Verstappen is the pick.",
        "band": "leaning",
        "factors": [
            {"key": "context", "direction": "up", "headline": "The pick",
             "text": "The model makes Max Verstappen the pick."},
            {"key": "context", "direction": "neutral", "headline": "Record",
             "text": "The model has done well here."},
        ],
        "source": "llm", "model": "m",
        "generated_at": "2026-09-29T00:00:00Z", "sport": "f1",
        "pick_timing": "unknown",
    }
    problems = validate(out, json.dumps(F1_FACTS), "[]")
    assert any("not established" in p for p in problems), (
        f"text that never says its timing is unverified was accepted: {problems}"
    )


def test_text_that_does_disclose_it_passes():
    """The control, and the reason the word list is a list rather than a flag."""
    from conftest import rule_validate as validate

    out = {
        "verdict": "Max Verstappen is the pick, though the timing is not verified.",
        "band": "leaning",
        "factors": [
            {"key": "context", "direction": "up", "headline": "The pick",
             "text": "The model makes Max Verstappen the pick."},
            {"key": "context", "direction": "neutral", "headline": "Timing",
             "text": "When this pick was made is not established."},
        ],
        "source": "llm", "model": "m",
        "generated_at": "2026-09-29T00:00:00Z", "sport": "f1",
        "pick_timing": "unknown",
    }
    assert validate(out, json.dumps(F1_FACTS), "[]") == []


def test_a_pre_kickoff_pick_is_not_required_to_disclose_anything():
    """The rule must not fire on a verified timing, or every summary grows a
    disclaimer nobody needs."""
    from conftest import rule_validate as validate

    out = {
        "verdict": "Max Verstappen is the pick.",
        "band": "leaning",
        "factors": [
            {"key": "context", "direction": "up", "headline": "The pick",
             "text": "The model makes Max Verstappen the pick."},
            {"key": "context", "direction": "neutral", "headline": "Record",
             "text": "The model has done well here."},
        ],
        "source": "llm", "model": "m",
        "generated_at": "2026-09-29T00:00:00Z", "sport": "f1",
        "pick_timing": "pre_kickoff",
    }
    assert validate(out, json.dumps({**F1_FACTS, "pick_timing": "pre_kickoff"}), "[]") == []


def test_a_bare_unknown_about_something_else_does_not_satisfy_the_rule():
    """CodeRabbit Major on the held PR: the old word list was subject-agnostic,
    so a factor saying "The weather is unknown." satisfied the disclosure rule
    without disclosing anything about when the pick was made. The rule now
    requires a timing-specific statement."""
    from conftest import rule_validate as validate

    out = {
        "verdict": "Max Verstappen is the pick.",
        "band": "leaning",
        "factors": [
            {"key": "context", "direction": "up", "headline": "The pick",
             "text": "The model makes Max Verstappen the pick."},
            {"key": "context", "direction": "neutral", "headline": "Weather",
             "text": "The weather is unknown."},
        ],
        "source": "llm", "model": "m",
        "generated_at": "2026-09-29T00:00:00Z", "sport": "f1",
        "pick_timing": "unknown",
    }
    problems = validate(out, json.dumps(F1_FACTS), "[]")
    assert any("not established" in p for p in problems), (
        f"a non-timing 'unknown' satisfied the disclosure rule: {problems}"
    )


def test_the_real_template_discloses_unknown_timing_and_passes_validation():
    """Through the REAL Facts model and the REAL template — no hand-built dict.

    The held PR's objection, reproduced first: with pick_timing "unknown" the
    template returned "Max Verstappen is the pick." with band "leaning" and no
    disclosure anywhere. Now the template carries a timing factor in the same
    words the validator requires, returns no band, and its own output passes
    validation."""
    from explainer.facts import Facts, render
    from explainer.template import explain_from_template
    from conftest import rule_validate as validate

    facts = Facts(**F1_FACTS)
    out = explain_from_template(facts.model_dump())
    text = " ".join(
        [out["verdict"]] + [f["headline"] + " " + f["text"] for f in out["factors"]]
    )
    assert "cannot be shown as made before" in text, (
        f"the template does not disclose the unverified timing: {text}"
    )
    assert out["band"] is None, (
        f"a confidence word on a pick the facts cannot place in time: {out['band']!r}"
    )
    # The template is not validated in production; this asks only whether its
    # timing disclosure satisfies the timing rule, so the figure rule is set aside.
    problems = [p for p in validate(
        {"verdict": out["verdict"], "band": out["band"], "factors": out["factors"]},
        render(facts), "[]",
    ) if not p.startswith("restates")]
    assert problems == [], f"the template's own disclosure fails validation: {problems}"


def test_the_real_service_withholds_the_band_for_unknown_timing():
    """The mutation that bit during the fix: `service._answer` overwrote the
    band unconditionally, so fixing only the template had no effect on what a
    reader receives. Driven through the real `_answer`, with a body that still
    claims "leaning", asserting on the response bytes."""
    from explainer.facts import Facts
    from explainer.service import Explainer
    from explainer.template import explain_from_template

    facts = Facts(**F1_FACTS)
    template_body = explain_from_template(facts.model_dump())
    row = {
        "source": "template", "model": "",
        "body": {**template_body, "band": "leaning"},
        "created_at": "2026-09-29T00:00:00+00:00", "prompt_version": "7",
    }
    out = Explainer._answer(Explainer.__new__(Explainer), "f1", "2026-16-race", row, facts)
    assert out["band"] is None, (
        f"the service restored a band the template withheld: {out['band']!r}"
    )
    assert out["pick_timing"] == "unknown"
    assert any(
        "cannot be shown as made before" in f.get("text", "")
        for f in out["factors"]
    ), "the disclosure factor did not survive the service"
