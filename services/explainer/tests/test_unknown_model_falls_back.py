"""A model that does not exist must cost the reader nothing.

The default free models were withdrawn from OpenRouter, and the product degraded
*silently*: a non-200 raises `LLMError`, which is caught, the fallback model is
tried, and if that fails too the template is stored. The reader sees a panel. The
only symptom is that every panel is a template, which looks like a design choice
rather than an outage.

So the fall-back-to-template path is right, and this file exists to keep it
right while the model ids change underneath it. Three things worth pinning that
the existing suite does not say:

* a 404 on the **primary** still tries the **fallback**, and a good answer from
  the fallback is used — a withdrawn primary must not cost the product its model
  summaries;
* a 404 on **both** produces a rendered panel, not an error, and the panel is
  the template's;
* and the stored row says the model was `unavailable`, not `llm`, so the footer
  fails closed. A row that claimed `llm` with a dead model would put "AI summary
  by <withdrawn model>" in front of a reader, which is the one claim in this
  product with no fact behind it.

The third case — that a template stored during an outage is *retried* once the
model comes back, rather than served forever — is already covered properly by
`test_a_template_made_in_an_outage_is_retried_later` in test_service.py, which
moves the retry window rather than asserting that two calls happened. A 404
variant of it was written here first and deleted: it asserted less and would
have passed whether or not the retry logic worked.
"""
import json

import httpx

from conftest import facts, good, make, reply
from explainer.llm import OPENROUTER_URL

FACTS_URL = "http://nfl.test/api/facts/g1"


def models_called(route):
    return [json.loads(c.request.content)["model"] for c in route.calls]


async def test_a_withdrawn_primary_still_reaches_the_fallback_model(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(
        side_effect=[
            httpx.Response(404, json={"error": {"message": "No endpoints found for deepseek/..."}}),
            reply(good()),
        ]
    )
    out = await make(tmp_path).explain("nfl", "g1")
    assert models_called(llm) == ["m1", "m2"], "the fallback was not tried after the primary 404'd"
    assert out["source"] == "llm" and out["model"] == "m2"


async def test_both_models_gone_is_a_rendered_panel_not_an_error(tmp_path, no_news):
    """The reader must get a panel either way. This is the whole point."""
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    gone = httpx.Response(404, json={"error": {"message": "No endpoints found"}})
    llm = no_news.post(OPENROUTER_URL).mock(side_effect=[gone, gone])

    out = await make(tmp_path).explain("nfl", "g1")

    assert llm.call_count == 2, "the fallback was skipped"
    assert out["source"] == "template"
    assert out["verdict"], "a template panel with no verdict renders as an empty box"
    assert out["factors"], "a template panel with no factors renders as an empty box"
    assert out["band"] in ("leaning", "moderate", "strong"), "a panel with no band cannot show a confidence"
    # _answer() blanks the model for a template row, so the panel's footer
    # cannot read "AI summary by <withdrawn model>".
    assert out["model"] == "", "a template row carried a model name, so the footer could claim AI wrote it"
