from __future__ import annotations

from dataclasses import dataclass
import re


# Map names carry qualifiers the walkthrough headings do not ("... Dungeon").
PLACE_QUALIFIERS = frozenset(("dungeon", "entrance", "exterior", "outside"))
GENERIC_PLACE_WORDS = frozenset(("a", "and", "cave", "near", "of", "the", "to"))


@dataclass(frozen=True, slots=True)
class GuideHeading:
    level: int
    title: str
    anchor: str


def guide_headings(markdown: str) -> tuple[GuideHeading, ...]:
    """Index the guide's headings with the anchors the overlay assigns them."""
    headings = []
    occurrences: dict[str, int] = {}
    fenced = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else re.match(r"(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if match is None or not match.group(2):
            continue
        title = match.group(2)
        slug = re.sub(r"[^\w -]", "", title.casefold()).replace(" ", "-")
        occurrence = occurrences.get(slug, 0)
        occurrences[slug] = occurrence + 1
        headings.append(GuideHeading(len(match.group(1)), title, f"{slug}-{occurrence}" if occurrence else slug))
    return tuple(headings)


def chapter_heading(headings: tuple[GuideHeading, ...], chapter: int) -> GuideHeading | None:
    prefix = f"chapter {chapter + 1}"
    return next((heading for heading in headings
                 if heading.level == 2 and re.match(rf"{prefix}\b", heading.title.casefold())), None)


def location_heading(headings: tuple[GuideHeading, ...], chapter: int, place: str) -> GuideHeading | None:
    """The first walkthrough step of this chapter that names the place."""
    start = chapter_heading(headings, chapter)
    words = [word for word in re.findall(r"[\w'-]+", place.casefold()) if word not in PLACE_QUALIFIERS]
    if start is None or not words:
        return None
    steps = []
    for heading in headings[headings.index(start) + 1:]:
        if heading.level == 2 and chapter < 4:
            break
        if heading.level == 3 and not heading.title.casefold().startswith("section achievements"):
            steps.append(heading)
    # The whole name first; a looser every-word match only when the name has
    # enough distinctive words to rule out look-alikes such as "Final ...".
    phrase = r"\b" + r"\W+".join(re.escape(word) for word in words) + r"\b"
    distinctive = tuple(word for word in words if word not in GENERIC_PLACE_WORDS)
    for heading in steps:
        if re.search(phrase, heading.title.casefold()):
            return heading
    if len(distinctive) >= 2:
        for heading in steps:
            if all(re.search(rf"\b{re.escape(word)}\b", heading.title.casefold()) for word in distinctive):
                return heading
    return None
