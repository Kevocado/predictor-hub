"""The frame has to ASK for news to be explained.

`prompts.SYSTEM` already says "using FACTS (our model's numbers) and NEWS (dated
headlines)" and already forbids inventing injuries. Neither of those asks for
news to be used: a headline can sit in the input and go unused, and the model is
then silent about a quarterback who will not play. This pins the instruction
that makes the headline the first thing a reader hears when it matters.

Two of these three are non-vacuous by construction: "lineup" appears nowhere in
the frame until the instruction lands, and the dating assertion names the exact
instruction phrase rather than the word "date" (which "dated headlines" in the
opening would otherwise satisfy without asking for anything).
"""
from explainer.prompts import SYSTEM


def test_the_frame_asks_for_lineup_news_to_be_explained():
    assert "lineup" in SYSTEM.lower() or "injury" in SYSTEM.lower(), (
        "the frame never mentions injury or lineup news, so the model is given "
        "headlines and no reason to use them"
    )


def test_the_frame_asks_for_the_news_to_be_dated():
    assert "date the news was published" in SYSTEM.lower(), (
        "a reader cannot judge a summary that does not say how old its news was; "
        "the opening line's 'dated headlines' describes the input without asking "
        "for the date to be stated"
    )


def test_the_frame_still_forbids_inventing_an_injury():
    """The prohibition is what makes the new instruction safe. Do not let a
    future edit satisfy the two tests above by dropping this."""
    assert "Never invent" in SYSTEM, (
        "the prohibition on inventing injuries was removed; the instruction to "
        "lead with news is only safe because the model may report a headline it "
        "was given and nothing else"
    )
