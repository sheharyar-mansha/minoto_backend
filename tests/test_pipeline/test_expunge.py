"""Unit tests for spoken 'expunge' command detection + application."""

from pipeline.expunge import apply_expunge_commands, is_expunge_command


def _seg(label, text, names=None):
    return {"speaker_label": label, "names": names or [], "text": text}


def test_is_expunge_command_matches_both_forms():
    assert is_expunge_command("expunge my last statement")
    assert is_expunge_command("Please expunge the last statement of Daniel.")
    assert not is_expunge_command("let's move on to the next item")


def test_my_redacts_own_previous_statement():
    segs = [
        _seg("A", "I think we should ship on Friday", ["Daniel"]),
        _seg("B", "I disagree, Monday is safer", ["Jessica"]),
        _seg("A", "expunge my last statement", ["Daniel"]),
    ]
    apply_expunge_commands(segs)
    assert segs[0]["is_expunged"] is True   # Daniel's own prior line
    assert segs[1]["is_expunged"] is False  # Jessica untouched
    assert segs[2]["is_command"] is True
    assert segs[2]["is_expunged"] is False


def test_named_redacts_that_persons_previous_statement():
    segs = [
        _seg("A", "the budget is forty thousand", ["Daniel"]),
        _seg("B", "I can start next week", ["Jessica"]),
        _seg("A", "expunge last statement of Jessica", ["Daniel"]),
    ]
    apply_expunge_commands(segs)
    assert segs[1]["is_expunged"] is True   # Jessica's line
    assert segs[0]["is_expunged"] is False  # Daniel's line untouched
    assert segs[2]["is_command"] is True


def test_named_matches_on_first_name_only():
    segs = [
        _seg("A", "sensitive detail here", ["Sara Khan"]),
        _seg("B", "expunge last statement of Sara", ["Daniel"]),
    ]
    apply_expunge_commands(segs)
    assert segs[0]["is_expunged"] is True


def test_named_unknown_person_is_noop_but_command_noted():
    segs = [
        _seg("A", "keep this", ["Daniel"]),
        _seg("B", "expunge last statement of Nobody", ["Jessica"]),
    ]
    apply_expunge_commands(segs)
    assert segs[0]["is_expunged"] is False
    assert segs[1]["is_command"] is True


def test_asr_only_single_speaker_my_still_works():
    # ASR-only transcript: every segment shares one (None) speaker.
    segs = [
        _seg(None, "first thing I said"),
        _seg(None, "expunge my last statement"),
    ]
    apply_expunge_commands(segs)
    assert segs[0]["is_expunged"] is True
    assert segs[1]["is_command"] is True


def test_multiple_commands_resolve_independently():
    segs = [
        _seg("A", "statement one", ["Daniel"]),
        _seg("A", "expunge my last statement", ["Daniel"]),  # -> redacts "statement one"
        _seg("A", "statement two", ["Daniel"]),
        _seg("A", "expunge my last statement", ["Daniel"]),  # -> redacts "statement two"
    ]
    apply_expunge_commands(segs)
    assert segs[0]["is_expunged"] is True
    assert segs[2]["is_expunged"] is True
    assert segs[1]["is_command"] and segs[3]["is_command"]


def test_command_with_no_prior_statement_is_safe():
    segs = [_seg("A", "expunge my last statement", ["Daniel"])]
    apply_expunge_commands(segs)
    assert segs[0]["is_command"] is True
    assert segs[0]["is_expunged"] is False


def test_plain_conversation_is_untouched():
    segs = [
        _seg("A", "good morning everyone", ["Daniel"]),
        _seg("B", "let's begin", ["Jessica"]),
    ]
    apply_expunge_commands(segs)
    assert all(not s["is_command"] and not s["is_expunged"] for s in segs)
