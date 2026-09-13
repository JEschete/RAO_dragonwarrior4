from game.achievements import ACHIEVEMENTS, ACHIEVEMENTS_BY_ID, TOTAL_POINTS


def test_achievement_catalog_matches_saved_set_totals() -> None:
    assert len(ACHIEVEMENTS) == 43
    assert len(ACHIEVEMENTS_BY_ID) == 43
    assert TOTAL_POINTS == 360
    assert ACHIEVEMENTS_BY_ID[52360].title == "Small Medal Collector"