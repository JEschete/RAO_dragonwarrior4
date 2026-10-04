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
        try:
            document = (
                MapDocument(
                    "Dragon Warrior IV Atlas",
                    assets.map_layers(),
                    ("collectibles", "entrance", "services", "locks", "hazards", "entities", "encounter-zone"),
                )
                if assets is not None
                else None
            )
        except (OSError, ValueError, IndexError) as failure:
            assets, document, error = None, None, f"Atlas unavailable: {failure}"
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
            assets = DragonWarrior4RomAssets(
                rom_path.expanduser(),
                context.state_directory,
                render_area_map,
                render_world_map,
                load_submap_names(context.repository_root),
            )
            if assets.region != "US":
                return None, f"This ROM version ({assets.region}) is not supported; maps and item data need the US version"
            return assets, ""
        except (OSError, ValueError, IndexError) as error:
            return None, str(error)


PLUGIN = Plugin()
