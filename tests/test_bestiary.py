from game.bestiary import resistance_lines


def test_resistances_keep_strength_and_name_only_the_classified_spells() -> None:
    resistances = (("Blaze", "Susceptible"), ("Sleep", "Partial resistance"),
                   ("Stopspell", "Strong resistance"), ("Beat", "Immune"))
    assert resistance_lines(resistances) == (
        "Vulnerable: Blaze", "Resists: Sleep", "Strongly resists: Stopspell", "Immune: Beat")
    assert resistance_lines(resistances, compact=True) == (
        "Resists: Sleep", "Strongly resists: Stopspell", "Immune: Beat")
    assert resistance_lines((("Blaze", "Immune"),)) == ("Immune: Blaze",)
    assert resistance_lines(()) == ()