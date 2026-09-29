"""The default free models must exist on OpenRouter, and the fallback too.

Both defaults were removed from OpenRouter's free tier, so every request to the
primary 404'd and every request to the fallback 404'd after it. The service did
not crash and did not log loudly: it stored a template row and carried on, so the
panel quietly degraded to the template for every fixture and nothing alerted.

This test cannot reach the network — it is a suite, and a test that calls
OpenRouter is a test that fails on a bad afternoon and costs a quota every run.
So it pins what *can* be checked offline, and the actual liveness check is a
documented manual step in the README, run from a machine that can reach
OpenRouter. What is pinned here is the part that silently rots:

* a default is not one of the ids that were withdrawn;
* both defaults end in ``:free``, because the whole budget assumes it;
* they are different models, so the fallback is a fallback;
* and no default names a vendor's ``free`` alias that has already been retired.

The withdrawn list is the useful part. It is a small, dated, factual record, and
it is what turns "someone changed the default to a dead model again" from an
incident into a failing test.
"""
from __future__ import annotations

import pytest

from explainer.config import Settings

# Ids that were the defaults and were withdrawn from OpenRouter's free tier.
# Dated because that is when it happened, not because the list expires.
WITHDRAWN = {
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-3.3-70b-instruct:free",
}

# Verified answering from the VPS, where the container has egress. Two of the
# candidates the reviewer tried were returning 429, which is a rate limit rather
# than a removal: a model can 429 today and be fine tomorrow, so 429 is not
# evidence of absence and is deliberately not recorded here.
VERIFIED = {
    "dots-studio/dots-3-note-preview:free",
    "poolside/laguna-s-2.1:free",
}


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_neither_default_is_a_withdrawn_model(settings):
    for field in (settings.model, settings.fallback_model):
        assert field not in WITHDRAWN, (
            f"{field!r} has been withdrawn from OpenRouter's free tier. The service does "
            f"not fail when a model 404s — it stores a template row and carries on, so a "
            f"dead default degrades the whole product silently. Pick an id verified from "
            f"a machine with egress and add it to VERIFIED."
        )


def test_both_defaults_are_free(settings):
    for field in (settings.model, settings.fallback_model):
        assert field.endswith(":free"), (
            f"{field!r} is not a free model. The daily cap is sized for the free tier; a "
            f"paid id would spend real money at a rate nothing here measures."
        )


def test_the_fallback_is_a_different_model(settings):
    assert settings.model != settings.fallback_model, (
        "the fallback is the same id as the primary, so a withdrawn or rate-limited "
        "model fails twice instead of once"
    )


def test_the_defaults_are_ones_somebody_verified(settings):
    # Deliberately a whitelist rather than a blacklist: an id nobody has seen
    # answer is the failure mode this whole file exists to prevent, and a
    # blacklist cannot catch it.
    for field in (settings.model, settings.fallback_model):
        assert field in VERIFIED, (
            f"{field!r} is not in VERIFIED. Add it only after watching it answer from a "
            f"machine with egress, and say when. An id nobody has run is an id nobody "
            f"knows works."
        )
