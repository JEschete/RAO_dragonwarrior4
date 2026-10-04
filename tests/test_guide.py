from pathlib import Path

from game.guide import chapter_heading, guide_headings, location_heading


ROOT = Path(__file__).parents[1]

SAMPLE = """# Walkthrough

## Table of Contents

## Chapter 1: Ragnar and the Missing Children

### Section Achievements: Chapter 1

### Burland Castle and Town

### Secret Playground

```
## not a heading
```

## Chapter 3: Taloon's Road to Riches

### Cave of the Silver Statuette

### Final Inventory Conversion

## Chapter 5 Begins: The Hero

### Burland Castle and Town

## Konenber and the Great Lighthouse

### Great Lighthouse
"""


def test_headings_carry_the_overlay_anchor_slugs_and_skip_code_fences() -> None:
    headings = guide_headings(SAMPLE)
    assert [heading.title for heading in headings if heading.level == 2][:2] == [
        "Table of Contents", "Chapter 1: Ragnar and the Missing Children"]
    assert all(heading.title != "not a heading" for heading in headings)
    anchors = [heading.anchor for heading in headings if heading.title == "Burland Castle and Town"]
    assert anchors == ["burland-castle-and-town", "burland-castle-and-town-1"]
    assert chapter_heading(headings, 2).anchor == "chapter-3-taloons-road-to-riches"
    assert chapter_heading(headings, 3) is None


def test_location_lookup_stays_inside_the_chapter_and_rejects_look_alikes() -> None:
    headings = guide_headings(SAMPLE)
    assert location_heading(headings, 0, "Burland").anchor == "burland-castle-and-town"
    assert location_heading(headings, 0, "Secret Playground Dungeon").title == "Secret Playground"
    assert location_heading(headings, 2, "Silver Statuette Cave").title == "Cave of the Silver Statuette"
    assert location_heading(headings, 2, "Final Cave") is None
    assert location_heading(headings, 2, "Burland") is None
    # Chapter 5 spans every later part of the walkthrough.
    assert location_heading(headings, 4, "Burland").anchor == "burland-castle-and-town-1"
    assert location_heading(headings, 4, "Lighthouse").title == "Great Lighthouse"
    assert location_heading(headings, 4, "Dungeon") is None


def test_shipped_guide_has_a_heading_for_every_chapter() -> None:
    headings = guide_headings((ROOT / "Guide" / "DW4_UnifiedGuide.md").read_text(encoding="utf-8"))
    assert all(chapter_heading(headings, chapter) is not None for chapter in range(5))
    assert len({heading.anchor for heading in headings}) == len(headings)
    assert location_heading(headings, 2, "Final Cave") is None
    assert location_heading(headings, 0, "Loch Tower").title == "Loch Tower"
