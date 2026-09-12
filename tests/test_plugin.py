from pathlib import Path

from retroarch_overlay.infrastructure.plugin_discovery import parse_plugin_manifest


def test_manifest() -> None:
    manifest = parse_plugin_manifest(Path(__file__).parents[1])
    assert manifest.slug == 'dragonwarrior4'
