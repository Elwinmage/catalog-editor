"""The user guides: one per language, linked from the README, every picture there."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDES = ROOT / "docs" / "guide"
LANGUAGES = ("en", "fr", "de", "es", "it", "nl", "pl", "pt")


def test_every_language_has_a_guide_linked_from_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for code in LANGUAGES:
        assert (GUIDES / f"guide.{code}.md").is_file(), code
        assert f"docs/guide/guide.{code}.md" in readme, code


def test_every_picture_of_a_guide_exists_and_all_guides_show_the_same_ones():
    shown = {}
    for code in LANGUAGES:
        text = (GUIDES / f"guide.{code}.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        assert links, code
        for link in links:
            assert (GUIDES / link).is_file(), f"{code}: {link}"
        shown[code] = [Path(link).name for link in links]
        # the guides link to each other
        for other in LANGUAGES:
            if other != code:
                assert f"guide.{other}.md" in text, f"{code} does not link to {other}"
    # translations follow the same outline: same pictures, same order
    assert all(names == shown["en"] for names in shown.values())
