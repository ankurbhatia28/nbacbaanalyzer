"""Identity resolution must never silently drop a player."""

from nbadata.ingest.resolve import ResolutionReport


def test_same_player_from_two_sources_merges_into_one_identity():
    r = ResolutionReport()
    r.observe("Nikola Jokić", "bbref", bbref_id="jokicni01")
    r.observe("Nikola Jokic", "fanspo", nba_id="203999")
    assert len(r.identities) == 1
    ident = r.identities["nikola jokic"]
    assert ident.bbref_id == "jokicni01"
    assert ident.nba_id == "203999"
    assert ident.seen_in == {"bbref", "fanspo"}


def test_preferred_id_favours_bbref():
    r = ResolutionReport()
    ident = r.observe("Trae Young", "fanspo", nba_id="1629027")
    assert ident.preferred_id == "1629027"
    r.observe("Trae Young", "bbref", bbref_id="youngtr01")
    assert ident.preferred_id == "youngtr01"


def test_first_id_wins_and_is_not_overwritten():
    r = ResolutionReport()
    r.observe("X Y", "a", bbref_id="first01")
    r.observe("X Y", "b", bbref_id="second01")
    assert r.identities["x y"].bbref_id == "first01"


def test_name_only_players_are_reported_not_dropped():
    """A player who vanishes during ingest becomes a wrong answer much later."""
    r = ResolutionReport()
    r.observe("Ghost Player", "spotrac")
    r.finalise()
    assert "ghost player" in r.unresolved
    assert r.summary["unresolved"] == 1


def test_empty_names_are_ignored():
    r = ResolutionReport()
    assert r.observe("", "x") is None
    assert not r.identities
