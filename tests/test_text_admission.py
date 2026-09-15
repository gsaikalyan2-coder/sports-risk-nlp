"""The admission gate: `src/dashboard/gibberish.py`.

Two properties, and they pull in opposite directions, which is the whole reason
this file is separate from `test_dashboard.py`:

* Junk must be refused, because an unrefused junk string produces an index of
  exactly 0.50 and a page that reports it.
* Real writing must be admitted, INCLUDING calm, short and off-topic writing.
  A gate that quietly rejects "slept well, the plan is clear" is not a safety
  feature, it is the system deciding what an athlete is allowed to have written.

The second set matters more. A false refusal is the app telling a person their
own words are not words; a false admission lands on a page already covered in
caveats. Both are tested, and the admitted set is deliberately the awkward one.
"""

from __future__ import annotations

import pytest

from src.dashboard.gibberish import (
    FUNCTION_WORDS,
    MIN_TOKENS,
    TextAdmission,
    admit,
)

REFUSED: tuple[tuple[str, str], ...] = (
    ("", "empty"),
    ("   \n\t ", "empty"),
    ("!!!! @@@ ### $$$ %%%%", "not_letters"),
    ("12345 67890 111 222 3333", "not_letters"),
    ("ok", "too_short"),
    ("Race day.", "too_short"),
    ("asdkjh qwe zzzz hjkl", "not_words"),
    ("xkcd zzzz brrr shhh mmm", "not_words"),
    ("no no no no no no no no no no", "repetition"),
    ("qwertyuiop asdfghjkl zxcvbnm poiuytrewq", "not_english"),
)

ADMITTED: tuple[str, ...] = (
    "I am terrified of tomorrow, my hands are shaking and I cannot sleep.",
    "Slept well. The plan is clear and I am looking forward to the final.",
    "It is just another race and I know what I have to do out there.",
    "the cat sat on the mat and then it went to sleep",
    "i dont know what to do about any of this if im honest with you",
    "My coach said the same thing to me before the last one, so it is fine.",
)


@pytest.mark.parametrize(("text", "reason"), REFUSED)
def test_junk_is_refused_with_the_right_reason(text: str, reason: str) -> None:
    """Refused, and refused for the reason a reader will be shown.

    The reason is asserted rather than just the refusal, because the reason is
    what the page prints. A gate that refuses everything for "not_english" is
    correct on the boolean and useless to the person reading it.
    """
    result = admit(text)
    assert not result.admitted
    assert not result, "TextAdmission must be falsey when it refuses"
    assert result.reason == reason
    assert result.detail.strip(), "a refusal with no explanation is not shippable"


@pytest.mark.parametrize("text", ADMITTED)
def test_real_writing_is_admitted(text: str) -> None:
    """Calm, short, off-topic and unpunctuated writing all get through.

    None of these should be scored highly. That is a different question, and it
    belongs to the scorer. The gate's only job is to agree that words were
    typed.
    """
    result = admit(text)
    assert result.admitted, f"{text!r} was refused: {result.reason} / {result.detail}"
    assert result.reason == "ok"
    assert result.detail == ""


def test_calm_text_is_not_treated_as_junk_for_lack_of_signal() -> None:
    """The gate tests for language, never for psychological content.

    This is the failure mode worth naming: it is tempting to refuse text that
    triggers no construct, because such text produces the same 0.50 an empty
    string does. It must not, because a genuinely untroubled athlete produces
    exactly that text, and refusing it would make the tool unable to report good
    news.
    """
    calm = "Everything is in order and I have done the work, so I am ready."
    assert admit(calm).admitted


def test_gate_runs_before_any_number_exists() -> None:
    """`admit` is pure, takes a string, and constructs nothing.

    Guards the ordering the page depends on. If this ever needed a backend, a
    view or a scorer, the refusal would be happening after a `DashboardView` had
    been built -- which is after the number it is refusing to show already
    exists.
    """
    result = admit("I am ready for tomorrow and the plan has not changed at all.")
    assert isinstance(result, TextAdmission)
    assert result.admitted


def test_thresholds_are_stated_not_buried() -> None:
    """The constants are importable, so a change to one is visible in a diff."""
    assert MIN_TOKENS >= 3
    assert "the" in FUNCTION_WORDS
    assert "anxiety" not in FUNCTION_WORDS, (
        "FUNCTION_WORDS must stay closed-class. A content word here would turn "
        "an is-this-English test into an is-this-about-sport test, which the "
        "gate is not entitled to ask."
    )


def test_refusal_text_carries_no_forbidden_vocabulary() -> None:
    """Every refusal string is a surface a reader sees, so it is screened too."""
    from src.dashboard.view import assert_no_forbidden_language

    for text, _ in REFUSED:
        assert_no_forbidden_language(admit(text).detail)
