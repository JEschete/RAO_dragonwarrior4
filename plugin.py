from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.models import MapDocument

from .game.adapter import Adapter
from .game.reference_data import load_submap_names
from .game.rom_assets import DragonWarrior4RomAssets
from .map_renderer import render_area_map, render_world_map


class Plugin:
    def create(self, context: GameContext) -> Adapter:
        if context.repository_root is None:
            raise ValueError("Dragon Warrior IV plugin repository root is required")
        assets, error = self._rom_assets(context)
        document = (
            MapDocument(
                "Dragon Warrior IV Atlas",
                assets.map_layers(),
                ("objective", "collectibles", "entrance"),
            )
            if assets is not None
            else None
        )
        return Adapter(context, assets, document, error)

    @staticmethod
    def _rom_assets(
        context: GameContext,
    ) -> tuple[DragonWarrior4RomAssets | None, str]:
        rom_path = context.settings.get("rom_path")
        if isinstance(rom_path, str) and rom_path.strip():
            rom_path = Path(rom_path)
        if not isinstance(rom_path, Path):
            return None, "Configure a Dragon Warrior IV ROM in Plugin Manager"
        if context.state_directory is None:
            return None, "Plugin state directory is unavailable"
        try:
            return (
                DragonWarrior4RomAssets(
                    rom_path,
                    context.state_directory,
                    render_area_map,
                    render_world_map,
                    load_submap_names(context.repository_root),
                ),
                "",
            )
        except (OSError, ValueError) as error:
            return None, str(error)


PLUGIN = Plugin()
