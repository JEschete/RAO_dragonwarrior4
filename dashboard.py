from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Literal

from PIL import Image, ImageTk


COLORS = {
    "ink": "#101412",
    "surface": "#18201b",
    "raised": "#232d25",
    "line": "#435146",
    "line_soft": "#303a32",
    "text": "#f2eee4",
    "muted": "#a8b1a7",
    "gold": "#d6ad50",
    "crimson": "#c95656",
    "teal": "#52a99d",
    "blue": "#6c9cc2",
    "green": "#72a96f",
    "violet": "#9b83b4",
    "white": "#ffffff",
}
FONTS = {
    "brand": ("Palatino Linotype", 22, "bold"),
    "title": ("Palatino Linotype", 17, "bold"),
    "heading": ("Bahnschrift SemiBold", 10),
    "body": ("Bahnschrift", 10),
    "small": ("Bahnschrift", 8),
    "metric": ("Bahnschrift SemiBold", 20),
}
WORKSPACES = (
    ("atlas", "ATLAS"),
    ("party", "PARTY"),
    ("journey", "JOURNEY"),
    ("journal", "JOURNAL"),
    ("encounters", "COMBAT LOG"),
    ("archive", "ARCHIVE"),
)
SIDEBAR_WIDTH = 184


def window_dimensions(
    screen_width: int,
    screen_height: int,
    tk_scaling: float,
) -> tuple[int, int, int, int]:
    ui_scale = max(1.0, tk_scaling / (96 / 72))
    width = min(round(1260 * ui_scale), round(screen_width * 0.92))
    height = min(round(790 * ui_scale), round(screen_height * 0.88))
    minimum_width = min(round(960 * ui_scale), width)
    minimum_height = min(round(620 * ui_scale), height)
    return width, height, minimum_width, minimum_height


def workspace_render_signature(workspace: str, live: dict[str, Any]) -> str:
    document = copy.deepcopy(live)
    location = document.get("location", {})
    if workspace == "atlas":
        location.pop("x", None)
        location.pop("y", None)
        payload: object = {
            "mode": document.get("mode"),
            "location": location,
            "features": [
                {
                    key: feature.get(key)
                    for key in ("id", "x", "y", "title", "kind", "marker")
                }
                for feature in document.get("atlas", {}).get("features", [])
            ],
            "reference": document.get("reference", {}),
        }
    elif workspace == "party":
        payload = [
            {
                key: member.get(key)
                for key in ("character_id", "name", "active")
            }
            for member in document.get("party", [])
        ]
    elif workspace == "journey":
        payload = {"chapter": document.get("journey", {}).get("chapter")}
    elif workspace == "journal":
        payload = {"workspace": "journal"}
    elif workspace == "encounters":
        payload = {"workspace": "encounters"}
    else:
        payload = document.get("reference", {})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def map_transform(
    image_size: tuple[int, int],
    canvas_size: tuple[int, int],
    player_pixel: tuple[float, float] | None,
    zoom: float,
) -> tuple[float, tuple[float, float]]:
    image_width, image_height = image_size
    canvas_width, canvas_height = canvas_size
    if min(image_width, image_height, canvas_width, canvas_height) <= 0:
        return 1.0, (0.0, 0.0)
    fit = min(canvas_width / image_width, canvas_height / image_height)
    scale = max(0.01, fit * max(1.0, zoom))
    rendered_width = image_width * scale
    rendered_height = image_height * scale
    if player_pixel is None or zoom <= 1.0:
        origin_x = (canvas_width - rendered_width) / 2
        origin_y = (canvas_height - rendered_height) / 2
    else:
        origin_x = canvas_width / 2 - player_pixel[0] * scale
        origin_y = canvas_height / 2 - player_pixel[1] * scale
        if rendered_width >= canvas_width:
            origin_x = min(0.0, max(canvas_width - rendered_width, origin_x))
        else:
            origin_x = (canvas_width - rendered_width) / 2
        if rendered_height >= canvas_height:
            origin_y = min(0.0, max(canvas_height - rendered_height, origin_y))
        else:
            origin_y = (canvas_height - rendered_height) / 2
    return scale, (origin_x, origin_y)


def feature_is_complete(
    feature: dict[str, Any],
    completed_feature_ids: set[str],
) -> bool:
    return bool(feature.get("completed")) or str(feature.get("id", "")) in completed_feature_ids


def feature_status(
    feature: dict[str, Any],
    completed_feature_ids: set[str],
) -> str:
    if feature.get("completed"):
        return "LOOTED IN GAME"
    if str(feature.get("id", "")) in completed_feature_ids:
        return "MARKED COMPLETE"
    return "AVAILABLE"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _open_url(url: str) -> None:
    webbrowser.open(url)


def _label(
    parent: tk.Misc,
    text: str,
    *,
    color: str = COLORS["text"],
    font: tuple[Any, ...] = FONTS["body"],
    background: str = COLORS["surface"],
    anchor: Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"] = "w",
    justify: Literal["left", "center", "right"] = "left",
    wraplength: int = 0,
) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        background=background,
        foreground=color,
        font=font,
        anchor=anchor,
        justify=justify,
        wraplength=wraplength,
    )


def _button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    active: bool = False,
    accent: str = COLORS["gold"],
    width: int = 0,
) -> tk.Button:
    return tk.Button(
        parent,
        text=text,
        command=command,
        background=accent if active else COLORS["raised"],
        foreground=COLORS["ink"] if active else COLORS["text"],
        activebackground=accent,
        activeforeground=COLORS["ink"],
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        font=FONTS["heading"],
        padx=11,
        pady=8,
        width=width,
        cursor="hand2",
    )


class ScrollPane(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        background: str = COLORS["ink"],
        width: int = 100,
    ) -> None:
        super().__init__(parent, background=background)
        self.canvas = tk.Canvas(
            self,
            width=width,
            background=background,
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="DW.Vertical.TScrollbar",
        )
        self.body = tk.Frame(self.canvas, background=background)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body.bind(
            "<Configure>",
            lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.window, width=event.width),
        )
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.body.bind("<MouseWheel>", self._wheel)

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


class Panel(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        *,
        subtitle: str = "",
        accent: str = COLORS["gold"],
        background: str = COLORS["surface"],
    ) -> None:
        super().__init__(
            parent,
            background=background,
            highlightbackground=COLORS["line"],
            highlightthickness=1,
            borderwidth=0,
        )
        heading = tk.Frame(self, background=background, padx=14, pady=10)
        heading.pack(fill="x")
        _label(
            heading,
            title.upper(),
            color=accent,
            font=FONTS["heading"],
            background=background,
        ).pack(side="left")
        if subtitle:
            self.subtitle_label = _label(
                heading,
                subtitle,
                color=COLORS["muted"],
                font=FONTS["small"],
                background=background,
                anchor="e",
            )
            self.subtitle_label.pack(side="right")
        else:
            self.subtitle_label = None
        tk.Frame(self, background=COLORS["line_soft"], height=1).pack(fill="x")
        self.body = tk.Frame(self, background=background, padx=14, pady=12)
        self.body.pack(fill="both", expand=True)


class Meter(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        value: float,
        *,
        color: str,
        height: int = 7,
    ) -> None:
        super().__init__(
            parent,
            width=100,
            height=height,
            background=COLORS["line_soft"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.value = max(0.0, min(1.0, value))
        self.color = color
        self.bind("<Configure>", self._draw)

    def _draw(self, event: tk.Event | None = None) -> None:
        self.delete("all")
        width = event.width if event is not None else self.winfo_width()
        height = event.height if event is not None else self.winfo_height()
        self.create_rectangle(
            0,
            0,
            width * self.value,
            height,
            fill=self.color,
            outline="",
        )

    def set(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))
        self._draw()


class CompanionDashboard:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.static_path = state_dir / "static.json"
        self.live_path = state_dir / "live.json"
        self.controls_path = state_dir / "controls.json"
        self.static = _read_json(self.static_path, {})
        self.live: dict[str, Any] = {}
        self.controls = _read_json(self.controls_path, {})
        self.controls["dashboard_open"] = True
        if not isinstance(self.controls.get("completed_features"), list):
            self.controls["completed_features"] = []
        _write_json(self.controls_path, self.controls)
        self.workspace = str(self.controls.get("workspace", "atlas"))
        if self.workspace not in dict(WORKSPACES):
            self.workspace = "atlas"
        self.zoom = 1.0
        self._live_stamp = -1
        self._render_signature = ""
        self._dynamic_widgets: dict[str, Any] = {}
        self._source_image_path = ""
        self._source_image_stamp = -1
        self._source_image: Image.Image | None = None
        self._map_photo_key: tuple[str, int, int] | None = None
        self._map_photo: ImageTk.PhotoImage | None = None
        self._atlas_scene_key: tuple[object, ...] | None = None
        self._atlas_items: dict[str, Any] = {}
        self._selected_feature_id: str | None = None
        self._tooltip: tk.Toplevel | None = None
        self._tooltip_label: tk.Label | None = None
        self._map_popout: tk.Toplevel | None = None
        self._popout_canvas: tk.Canvas | None = None
        self._popout_title: tk.Label | None = None
        self._popout_coordinates: tk.Label | None = None
        self._popout_feature: tk.Label | None = None
        self._popout_complete_button: tk.Button | None = None
        self._popout_zoom = 1.0
        self._popout_scene_key: tuple[object, ...] | None = None
        self._popout_items: dict[str, Any] = {}
        self._popout_photo_key: tuple[str, int, int] | None = None
        self._popout_photo: ImageTk.PhotoImage | None = None

        self.root = tk.Tk()
        self.root.title("Dragon Warrior IV Cartographer's Companion")
        width, height, minimum_width, minimum_height = window_dimensions(
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            float(self.root.tk.call("tk", "scaling")),
        )
        left = max(0, (self.root.winfo_screenwidth() - width) // 2)
        top = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.root.minsize(minimum_width, minimum_height)
        self.root.configure(background=COLORS["ink"])
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.attributes("-topmost", True)
        self._configure_styles()
        self._build_shell()
        self._render_waiting()
        self.root.after(100, self._poll)

    def run(self) -> None:
        self.root.mainloop()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "DW.Vertical.TScrollbar",
            troughcolor=COLORS["ink"],
            background=COLORS["line"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
        )

    def _build_shell(self) -> None:
        top = tk.Frame(self.root, background=COLORS["surface"], height=82)
        top.pack(fill="x")
        top.pack_propagate(False)
        brand = tk.Frame(top, background=COLORS["surface"], padx=22, pady=13)
        brand.pack(side="left")
        _label(
            brand,
            "DRAGON WARRIOR IV",
            color=COLORS["gold"],
            font=FONTS["brand"],
            background=COLORS["surface"],
        ).pack(anchor="w")
        _label(
            brand,
            "CARTOGRAPHER'S COMPANION",
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["surface"],
        ).pack(anchor="w")
        status = tk.Frame(top, background=COLORS["surface"], padx=22, pady=15)
        status.pack(side="right", fill="y")
        self.location_label = _label(
            status,
            "Waiting for game",
            font=FONTS["heading"],
            background=COLORS["surface"],
            anchor="e",
        )
        self.location_label.pack(anchor="e")
        self.connection_label = _label(
            status,
            "OFFLINE",
            color=COLORS["crimson"],
            font=FONTS["small"],
            background=COLORS["surface"],
            anchor="e",
        )
        self.connection_label.pack(anchor="e", pady=(6, 0))
        tk.Frame(self.root, background=COLORS["gold"], height=2).pack(fill="x")

        shell = tk.Frame(self.root, background=COLORS["ink"])
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, background=COLORS["surface"], width=SIDEBAR_WIDTH)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        _label(
            sidebar,
            "WORKSPACES",
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["surface"],
        ).pack(fill="x", padx=18, pady=(24, 10))
        self.nav_buttons: dict[str, tk.Button] = {}
        accents = {
            "atlas": COLORS["gold"],
            "party": COLORS["teal"],
            "journey": COLORS["crimson"],
            "journal": COLORS["blue"],
            "encounters": COLORS["crimson"],
            "archive": COLORS["violet"],
        }
        for key, label in WORKSPACES:
            button = _button(
                sidebar,
                label,
                lambda selected=key: self._select_workspace(selected),
                active=key == self.workspace,
                accent=accents[key],
                width=17,
            )
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = button
        footer = tk.Frame(sidebar, background=COLORS["surface"], padx=18, pady=18)
        footer.pack(side="bottom", fill="x")
        self.mode_label = _label(
            footer,
            "NO SIGNAL",
            color=COLORS["muted"],
            font=FONTS["heading"],
            background=COLORS["surface"],
        )
        self.mode_label.pack(anchor="w")
        self.source_label = _label(
            footer,
            "Memory: -- / ROM: --",
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["surface"],
            wraplength=145,
        )
        self.source_label.pack(anchor="w", pady=(5, 0))

        self.workspace_host = tk.Frame(shell, background=COLORS["ink"])
        self.workspace_host.pack(side="left", fill="both", expand=True)

    def _select_workspace(self, workspace: str) -> None:
        if workspace not in dict(WORKSPACES):
            return
        self.workspace = workspace
        self.controls["workspace"] = workspace
        _write_json(self.controls_path, self.controls)
        accents = {
            "atlas": COLORS["gold"],
            "party": COLORS["teal"],
            "journey": COLORS["crimson"],
            "journal": COLORS["blue"],
            "encounters": COLORS["crimson"],
            "archive": COLORS["violet"],
        }
        for key, button in self.nav_buttons.items():
            active = key == workspace
            button.configure(
                background=accents[key] if active else COLORS["raised"],
                foreground=COLORS["ink"] if active else COLORS["text"],
            )
        self._render_signature = ""
        self._render_workspace()

    def _render_waiting(self) -> None:
        self._clear_workspace()
        body = tk.Frame(self.workspace_host, background=COLORS["ink"], padx=32, pady=32)
        body.pack(fill="both", expand=True)
        _label(
            body,
            "THE ATLAS IS QUIET",
            color=COLORS["gold"],
            font=FONTS["title"],
            background=COLORS["ink"],
        ).pack(anchor="w", pady=(80, 8))
        _label(
            body,
            "Waiting for a readable Dragon Warrior IV game state.",
            color=COLORS["muted"],
            background=COLORS["ink"],
        ).pack(anchor="w")

    def _clear_workspace(self) -> None:
        self._hide_tooltip()
        for child in self.workspace_host.winfo_children():
            child.destroy()
        self._dynamic_widgets = {}
        self._atlas_scene_key = None
        self._atlas_items = {}

    def _render_workspace(self) -> None:
        if not self.live or self.live.get("mode") == "waiting":
            self._render_waiting()
            return
        self._clear_workspace()
        if self.workspace == "atlas":
            self._render_atlas()
        elif self.workspace == "party":
            self._render_party()
        elif self.workspace == "journey":
            self._render_journey()
        elif self.workspace == "journal":
            self._render_journal()
        elif self.workspace == "encounters":
            self._render_encounters()
        else:
            self._render_archive()
        self._render_signature = workspace_render_signature(self.workspace, self.live)

    def _page_heading(self, parent: tk.Misc, title: str, subtitle: str) -> None:
        heading = tk.Frame(parent, background=COLORS["ink"])
        heading.pack(fill="x", pady=(0, 16))
        _label(
            heading,
            title,
            font=FONTS["title"],
            background=COLORS["ink"],
        ).pack(anchor="w")
        _label(
            heading,
            subtitle,
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["ink"],
        ).pack(anchor="w", pady=(3, 0))

    def _render_atlas(self) -> None:
        page = tk.Frame(self.workspace_host, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        self._page_heading(page, "Living Atlas", "ROM terrain / live position / map features")
        body = tk.Frame(page, background=COLORS["ink"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3, minsize=520)
        body.grid_columnconfigure(1, weight=1, minsize=260)
        body.grid_rowconfigure(0, weight=1)

        map_panel = Panel(body, "Current map", accent=COLORS["gold"])
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        toolbar = tk.Frame(map_panel.body, background=COLORS["surface"])
        toolbar.pack(fill="x", pady=(0, 10))
        self._dynamic_widgets["atlas_title"] = _label(
            toolbar,
            str(self.live.get("location", {}).get("title", "Unknown map")),
            font=FONTS["heading"],
        )
        self._dynamic_widgets["atlas_title"].pack(side="left")
        self._dynamic_widgets["coordinates"] = _label(
            toolbar,
            self._coordinates_text(),
            color=COLORS["teal"],
            font=FONTS["heading"],
            anchor="e",
        )
        self._dynamic_widgets["coordinates"].pack(side="right", padx=(10, 0))
        _button(
            toolbar,
            "POPOUT",
            self._open_map_popout,
            accent=COLORS["blue"],
        ).pack(side="right", padx=(10, 0))
        _button(toolbar, "+", lambda: self._set_zoom(self.zoom + 0.5), width=2).pack(
            side="right", padx=(4, 0)
        )
        _button(toolbar, "-", lambda: self._set_zoom(self.zoom - 0.5), width=2).pack(
            side="right", padx=(10, 0)
        )
        self._dynamic_widgets["zoom"] = _label(
            toolbar,
            f"{int(self.zoom * 100)}%",
            color=COLORS["muted"],
            font=FONTS["small"],
            anchor="e",
        )
        self._dynamic_widgets["zoom"].pack(side="right", padx=(8, 0))
        canvas = tk.Canvas(
            map_panel.body,
            background="#0b0f0c",
            highlightbackground=COLORS["line_soft"],
            highlightthickness=1,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Configure>", lambda _: self._draw_atlas())
        self._dynamic_widgets["atlas_canvas"] = canvas

        rail = ScrollPane(body, background=COLORS["ink"], width=220)
        rail.grid(row=0, column=1, sticky="nsew")
        current = Panel(rail.body, "Position", accent=COLORS["teal"])
        current.pack(fill="x", pady=(0, 12))
        location = self.live.get("location", {})
        _label(
            current.body,
            str(location.get("title", "Unknown")),
            background=COLORS["surface"],
            wraplength=220,
        ).pack(fill="x", pady=2)
        self._dynamic_widgets["position_coordinates"] = _label(
            current.body,
            self._coordinates_text(),
            color=COLORS["teal"],
            background=COLORS["surface"],
            wraplength=220,
        )
        self._dynamic_widgets["position_coordinates"].pack(fill="x", pady=2)
        _label(
            current.body,
            str(location.get("evidence", "")),
            color=COLORS["muted"],
            background=COLORS["surface"],
            wraplength=220,
        ).pack(fill="x", pady=2)

        features = Panel(
            rail.body,
            "Map features",
            subtitle=str(len(self.live.get("atlas", {}).get("features", []))),
            accent=COLORS["crimson"],
        )
        features.pack(fill="x", pady=(0, 12))
        feature_rows = self.live.get("atlas", {}).get("features", [])
        feature_variables: dict[str, tk.BooleanVar] = {}
        feature_controls: dict[str, tk.Widget] = {}
        if not feature_rows:
            _label(
                features.body,
                "No documented feature tiles on this layer",
                color=COLORS["muted"],
                background=COLORS["surface"],
                wraplength=220,
            ).pack(fill="x")
        for feature in feature_rows[:18]:
            row = tk.Frame(features.body, background=COLORS["surface"])
            row.pack(fill="x", pady=3)
            kind = str(feature.get("kind", "point"))
            color = self._feature_color(kind)
            tk.Frame(row, width=4, background=color).pack(side="left", fill="y")
            feature_id = str(feature.get("id", ""))
            label = (
                f"{feature.get('title', 'Feature')}  "
                f"({feature.get('x', 0)},{feature.get('y', 0)})"
            )
            if self._feature_is_completable(feature):
                variable = tk.BooleanVar(
                    value=feature_is_complete(
                        feature,
                        self._completed_feature_ids(),
                    )
                )
                control: tk.Widget = tk.Checkbutton(
                    row,
                    text=label,
                    variable=variable,
                    command=lambda selected=feature_id: self._toggle_feature(selected),
                    background=COLORS["surface"],
                    foreground=COLORS["text"],
                    activebackground=COLORS["surface"],
                    activeforeground=COLORS["text"],
                    selectcolor=COLORS["raised"],
                    font=FONTS["small"],
                    anchor="w",
                    justify="left",
                    wraplength=190,
                    cursor="hand2",
                    highlightthickness=0,
                    borderwidth=0,
                )
                feature_variables[feature_id] = variable
            else:
                control = _label(
                    row,
                    label,
                    font=FONTS["small"],
                    background=COLORS["surface"],
                    wraplength=190,
                )
            control.pack(side="left", fill="x", expand=True, padx=(8, 0))
            control.bind(
                "<Enter>",
                lambda event, selected=feature_id: self._show_feature_tooltip(
                    selected,
                    event,
                ),
            )
            control.bind(
                "<Motion>",
                lambda event, selected=feature_id: self._show_feature_tooltip(
                    selected,
                    event,
                ),
            )
            control.bind("<Leave>", lambda _: self._hide_tooltip())
            feature_controls[feature_id] = control
        self._dynamic_widgets["feature_variables"] = feature_variables
        self._dynamic_widgets["feature_controls"] = feature_controls

        detail_panel = Panel(rail.body, "Feature detail", accent=COLORS["gold"])
        detail_panel.pack(fill="x", pady=(0, 12))
        self._dynamic_widgets["feature_detail_title"] = _label(
            detail_panel.body,
            "Hover a map marker",
            font=FONTS["heading"],
            background=COLORS["surface"],
            wraplength=220,
        )
        self._dynamic_widgets["feature_detail_title"].pack(fill="x")
        self._dynamic_widgets["feature_detail_status"] = _label(
            detail_panel.body,
            "",
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["surface"],
            wraplength=220,
        )
        self._dynamic_widgets["feature_detail_status"].pack(fill="x", pady=(4, 0))
        self._dynamic_widgets["feature_detail_text"] = _label(
            detail_panel.body,
            "Chest contents and map details appear here.",
            color=COLORS["muted"],
            background=COLORS["surface"],
            wraplength=220,
        )
        self._dynamic_widgets["feature_detail_text"].pack(fill="x", pady=(5, 0))
        self._dynamic_widgets["feature_detail_button"] = _button(
            detail_panel.body,
            "MARK COMPLETE",
            self._toggle_selected_feature,
            accent=COLORS["green"],
        )
        self._dynamic_widgets["feature_detail_button"].pack(fill="x", pady=(10, 0))

        dialogue_panel = Panel(rail.body, "Current dialogue", accent=COLORS["violet"])
        dialogue_panel.pack(fill="x", pady=(0, 12))
        self._dynamic_widgets["dialogue"] = _label(
            dialogue_panel.body,
            str(self.live.get("dialogue", "")).strip() or "No active dialogue",
            color=(
                COLORS["text"]
                if str(self.live.get("dialogue", "")).strip()
                else COLORS["muted"]
            ),
            background=COLORS["surface"],
            wraplength=220,
        )
        self._dynamic_widgets["dialogue"].pack(fill="x")
        self._update_feature_detail()
        self.root.after_idle(self._draw_atlas)

    def _completed_feature_ids(self) -> set[str]:
        values = self.controls.get("completed_features", [])
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values if isinstance(value, str)}

    def _feature_by_id(self, feature_id: str) -> dict[str, Any] | None:
        return next(
            (
                feature
                for feature in self.live.get("atlas", {}).get("features", [])
                if str(feature.get("id", "")) == feature_id
            ),
            None,
        )

    @staticmethod
    def _feature_is_completable(feature: dict[str, Any]) -> bool:
        return str(feature.get("kind", "")) in {"collectibles", "objective"}

    def _toggle_feature(self, feature_id: str) -> None:
        feature = self._feature_by_id(feature_id)
        if (
            feature is None
            or not self._feature_is_completable(feature)
            or bool(feature.get("completed"))
        ):
            self._update_atlas()
            return
        completed = self._completed_feature_ids()
        if feature_id in completed:
            completed.remove(feature_id)
        else:
            completed.add(feature_id)
        self.controls["completed_features"] = sorted(completed)
        _write_json(self.controls_path, self.controls)
        self._selected_feature_id = feature_id
        self._update_atlas()
        self._update_map_popout()

    def _toggle_selected_feature(self) -> None:
        if self._selected_feature_id is not None:
            self._toggle_feature(self._selected_feature_id)

    def _select_feature(self, feature_id: str) -> None:
        self._selected_feature_id = feature_id
        self._update_feature_detail()
        self._update_map_popout()

    def _update_feature_detail(self) -> None:
        title = self._dynamic_widgets.get("feature_detail_title")
        status = self._dynamic_widgets.get("feature_detail_status")
        detail = self._dynamic_widgets.get("feature_detail_text")
        button = self._dynamic_widgets.get("feature_detail_button")
        if not isinstance(title, tk.Label):
            return
        if not isinstance(status, tk.Label):
            return
        if not isinstance(detail, tk.Label):
            return
        if not isinstance(button, tk.Button):
            return
        feature = (
            self._feature_by_id(self._selected_feature_id)
            if self._selected_feature_id is not None
            else None
        )
        if feature is None:
            title.configure(text="Hover a map marker")
            status.configure(text="", foreground=COLORS["muted"])
            detail.configure(
                text="Chest contents and map details appear here.",
                foreground=COLORS["muted"],
            )
            button.configure(text="MARK COMPLETE", state="disabled")
            return
        completed = self._completed_feature_ids()
        state = feature_status(feature, completed)
        title.configure(text=str(feature.get("title", "Feature")))
        status.configure(
            text=state,
            foreground=(
                COLORS["green"]
                if feature_is_complete(feature, completed)
                else COLORS["gold"]
            ),
        )
        detail.configure(
            text=str(feature.get("detail", "No additional details")),
            foreground=COLORS["text"],
        )
        if not self._feature_is_completable(feature):
            button.configure(text="REFERENCE POINT", state="disabled")
        elif feature.get("completed"):
            button.configure(text="LOOTED IN GAME", state="disabled")
        else:
            button.configure(
                text=(
                    "MARK INCOMPLETE"
                    if str(feature.get("id", "")) in completed
                    else "MARK COMPLETE"
                ),
                state="normal",
            )

    def _tooltip_text(self, feature: dict[str, Any]) -> str:
        status = feature_status(feature, self._completed_feature_ids())
        detail = str(feature.get("detail", "No additional details"))
        return f"{feature.get('title', 'Feature')}\n{status}\n\n{detail}"

    def _show_feature_tooltip(
        self,
        feature_id: str,
        _: tk.Event | None = None,
    ) -> None:
        feature = self._feature_by_id(feature_id)
        if feature is None:
            return
        self._select_feature(feature_id)
        if self._tooltip is None or not self._tooltip.winfo_exists():
            self._tooltip = tk.Toplevel(self.root)
            self._tooltip.withdraw()
            self._tooltip.overrideredirect(True)
            self._tooltip.attributes("-topmost", True)
            self._tooltip_label = tk.Label(
                self._tooltip,
                background=COLORS["raised"],
                foreground=COLORS["text"],
                font=FONTS["body"],
                justify="left",
                anchor="nw",
                wraplength=360,
                padx=12,
                pady=10,
                highlightbackground=COLORS["gold"],
                highlightthickness=1,
                borderwidth=0,
            )
            self._tooltip_label.pack(fill="both", expand=True)
        assert self._tooltip_label is not None and self._tooltip is not None
        self._tooltip_label.configure(text=self._tooltip_text(feature))
        self._tooltip.update_idletasks()
        left = self.root.winfo_pointerx() + 14
        top = self.root.winfo_pointery() + 16
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        left = min(left, screen_width - self._tooltip.winfo_reqwidth() - 8)
        top = min(top, screen_height - self._tooltip.winfo_reqheight() - 8)
        self._tooltip.geometry(f"+{max(0, left)}+{max(0, top)}")
        self._tooltip.deiconify()

    def _hide_tooltip(self) -> None:
        tooltip = getattr(self, "_tooltip", None)
        if tooltip is not None and tooltip.winfo_exists():
            tooltip.withdraw()

    def _update_atlas(self) -> None:
        coordinates = self._coordinates_text()
        for key in ("coordinates", "position_coordinates"):
            widget = self._dynamic_widgets.get(key)
            if widget is not None:
                widget.configure(text=coordinates)
        dialogue = str(self.live.get("dialogue", "")).strip()
        dialogue_label = self._dynamic_widgets.get("dialogue")
        if dialogue_label is not None:
            dialogue_label.configure(
                text=dialogue or "No active dialogue",
                foreground=COLORS["text"] if dialogue else COLORS["muted"],
            )
        completed = self._completed_feature_ids()
        variables = self._dynamic_widgets.get("feature_variables", {})
        controls = self._dynamic_widgets.get("feature_controls", {})
        for feature in self.live.get("atlas", {}).get("features", []):
            feature_id = str(feature.get("id", ""))
            complete = feature_is_complete(feature, completed)
            variable = variables.get(feature_id)
            if variable is not None:
                variable.set(complete)
            control = controls.get(feature_id)
            if isinstance(control, tk.Checkbutton):
                control.configure(
                    state="disabled" if feature.get("completed") else "normal",
                    disabledforeground=COLORS["green"],
                    foreground=COLORS["green"] if complete else COLORS["text"],
                )
        self._update_feature_detail()
        if self._tooltip is not None and self._tooltip.winfo_viewable():
            if self._selected_feature_id is not None:
                self._show_feature_tooltip(self._selected_feature_id)
        self._draw_atlas()

    def _set_zoom(self, value: float) -> None:
        self.zoom = max(1.0, min(4.0, value))
        label = self._dynamic_widgets.get("zoom")
        if label is not None:
            label.configure(text=f"{int(self.zoom * 100)}%")
        self._draw_atlas()

    def _open_map_popout(self) -> None:
        if self._map_popout is not None and self._map_popout.winfo_exists():
            self._map_popout.deiconify()
            self._map_popout.lift()
            self._update_map_popout()
            return
        window = tk.Toplevel(self.root)
        self._map_popout = window
        window.title("Dragon Warrior IV · Map")
        width = min(1100, round(window.winfo_screenwidth() * 0.82))
        height = min(850, round(window.winfo_screenheight() * 0.82))
        left = max(0, (window.winfo_screenwidth() - width) // 2)
        top = max(0, (window.winfo_screenheight() - height) // 2)
        window.geometry(f"{width}x{height}+{left}+{top}")
        window.minsize(640, 480)
        window.configure(background=COLORS["ink"])
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._close_map_popout)

        toolbar = tk.Frame(window, background=COLORS["surface"], padx=16, pady=11)
        toolbar.pack(fill="x")
        self._popout_title = _label(
            toolbar,
            str(self.live.get("location", {}).get("title", "Map")),
            color=COLORS["gold"],
            font=FONTS["heading"],
            background=COLORS["surface"],
        )
        self._popout_title.pack(side="left")
        self._popout_coordinates = _label(
            toolbar,
            self._coordinates_text(),
            color=COLORS["teal"],
            font=FONTS["heading"],
            background=COLORS["surface"],
            anchor="e",
        )
        self._popout_coordinates.pack(side="right", padx=(12, 0))
        _button(
            toolbar,
            "+",
            lambda: self._set_popout_zoom(self._popout_zoom + 0.5),
            width=2,
        ).pack(side="right", padx=(4, 0))
        _button(
            toolbar,
            "-",
            lambda: self._set_popout_zoom(self._popout_zoom - 0.5),
            width=2,
        ).pack(side="right", padx=(12, 0))

        self._popout_canvas = tk.Canvas(
            window,
            background="#0b0f0c",
            highlightthickness=0,
            borderwidth=0,
        )
        self._popout_canvas.pack(fill="both", expand=True)
        self._popout_canvas.bind("<Configure>", lambda _: self._draw_map_popout())
        footer = tk.Frame(window, background=COLORS["surface"], padx=16, pady=10)
        footer.pack(fill="x")
        self._popout_feature = _label(
            footer,
            "Hover a marker for details",
            color=COLORS["muted"],
            background=COLORS["surface"],
            wraplength=max(320, width - 300),
        )
        self._popout_feature.pack(side="left", fill="x", expand=True)
        self._popout_complete_button = _button(
            footer,
            "MARK COMPLETE",
            self._toggle_selected_feature,
            accent=COLORS["green"],
        )
        self._popout_complete_button.pack(side="right", padx=(12, 0))
        self._update_map_popout()
        window.after_idle(self._draw_map_popout)

    def _close_map_popout(self) -> None:
        window = self._map_popout
        self._map_popout = None
        self._popout_canvas = None
        self._popout_title = None
        self._popout_coordinates = None
        self._popout_feature = None
        self._popout_complete_button = None
        self._popout_scene_key = None
        self._popout_items = {}
        self._popout_photo_key = None
        self._popout_photo = None
        if window is not None and window.winfo_exists():
            window.destroy()

    def _set_popout_zoom(self, value: float) -> None:
        self._popout_zoom = max(1.0, min(8.0, value))
        self._draw_map_popout()

    def _draw_atlas(self) -> None:
        canvas = self._dynamic_widgets.get("atlas_canvas")
        if not isinstance(canvas, tk.Canvas):
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        location = self.live.get("location", {})
        image_path = str(location.get("image_path", ""))
        source = self._load_source_image(image_path)
        if source is None:
            scene_key = ("missing", width, height)
            if scene_key != self._atlas_scene_key:
                canvas.delete("all")
                self._atlas_items = {
                    "message": canvas.create_text(
                        width / 2,
                        height / 2,
                        text="ROM ATLAS IMAGE UNAVAILABLE",
                        fill=COLORS["muted"],
                        font=FONTS["heading"],
                    )
                }
                self._atlas_scene_key = scene_key
            return
        metadata = next(
            (
                item
                for item in self.static.get("maps", [])
                if item.get("key") == location.get("map_key")
            ),
            {},
        )
        tile_width = int(metadata.get("tile_width", 16))
        tile_height = int(metadata.get("tile_height", 16))
        player_pixel = (
            (float(location.get("x", 0)) + 0.5) * tile_width,
            (float(location.get("y", 0)) + 0.5) * tile_height,
        )
        scale, (origin_x, origin_y) = map_transform(
            source.size,
            (width, height),
            player_pixel,
            self.zoom,
        )
        resized = (
            max(1, round(source.width * scale)),
            max(1, round(source.height * scale)),
        )
        photo_key = (image_path, *resized)
        if photo_key != self._map_photo_key:
            display = source.resize(resized, Image.Resampling.NEAREST)
            self._map_photo = ImageTk.PhotoImage(display)
            self._map_photo_key = photo_key
        assert self._map_photo is not None
        features = self.live.get("atlas", {}).get("features", [])
        scene_key = (
            image_path,
            self._source_image_stamp,
            width,
            height,
            resized,
            tuple(
                (
                    str(feature.get("id", "")),
                    feature.get("x"),
                    feature.get("y"),
                    feature.get("kind"),
                )
                for feature in features
            ),
        )
        if scene_key != self._atlas_scene_key:
            canvas.delete("all")
            image_item = canvas.create_image(
                origin_x,
                origin_y,
                image=self._map_photo,
                anchor="nw",
            )
            feature_items: dict[str, int] = {}
            for feature in features:
                feature_id = str(feature.get("id", ""))
                item = canvas.create_oval(0, 0, 0, 0, width=1)
                canvas.tag_bind(
                    item,
                    "<Enter>",
                    lambda event, selected=feature_id: self._show_feature_tooltip(
                        selected,
                        event,
                    ),
                )
                canvas.tag_bind(
                    item,
                    "<Motion>",
                    lambda event, selected=feature_id: self._show_feature_tooltip(
                        selected,
                        event,
                    ),
                )
                canvas.tag_bind(item, "<Leave>", lambda _: self._hide_tooltip())
                canvas.tag_bind(
                    item,
                    "<Button-1>",
                    lambda _, selected=feature_id: self._select_feature(selected),
                )
                feature_items[feature_id] = item
            self._atlas_items = {
                "image": image_item,
                "features": feature_items,
                "player_outer": canvas.create_oval(0, 0, 0, 0, width=3),
                "player_inner": canvas.create_oval(0, 0, 0, 0, outline=""),
            }
            self._atlas_scene_key = scene_key

        canvas.coords(self._atlas_items["image"], origin_x, origin_y)
        completed = self._completed_feature_ids()
        feature_items = self._atlas_items.get("features", {})
        for feature in features:
            feature_id = str(feature.get("id", ""))
            item = feature_items.get(feature_id)
            if item is None:
                continue
            feature_x = origin_x + (float(feature.get("x", 0)) + 0.5) * tile_width * scale
            feature_y = origin_y + (float(feature.get("y", 0)) + 0.5) * tile_height * scale
            radius = max(5.0, min(9.0, tile_width * scale * 0.32))
            complete = feature_is_complete(feature, completed)
            color = (
                COLORS["green"]
                if complete
                else self._feature_color(str(feature.get("kind", "point")))
            )
            canvas.coords(
                item,
                feature_x - radius,
                feature_y - radius,
                feature_x + radius,
                feature_y + radius,
            )
            canvas.itemconfigure(
                item,
                fill=color,
                outline=COLORS["white"] if complete else COLORS["ink"],
            )
        player_x = origin_x + player_pixel[0] * scale
        player_y = origin_y + player_pixel[1] * scale
        radius = max(5.0, min(10.0, tile_width * scale * 0.4))
        canvas.coords(
            self._atlas_items["player_outer"],
            player_x - radius,
            player_y - radius,
            player_x + radius,
            player_y + radius,
        )
        canvas.itemconfigure(
            self._atlas_items["player_outer"],
            fill=COLORS["white"],
            outline=COLORS["crimson"],
        )
        canvas.coords(
            self._atlas_items["player_inner"],
            player_x - 2,
            player_y - 2,
            player_x + 2,
            player_y + 2,
        )
        canvas.itemconfigure(
            self._atlas_items["player_inner"],
            fill=COLORS["crimson"],
        )

    def _show_popout_feature(
        self,
        feature_id: str,
        event: tk.Event | None = None,
    ) -> None:
        self._selected_feature_id = feature_id
        self._update_feature_detail()
        self._update_map_popout()
        self._show_feature_tooltip(feature_id, event)

    def _update_map_popout(self) -> None:
        window = getattr(self, "_map_popout", None)
        if window is None or not window.winfo_exists():
            return
        location = self.live.get("location", {})
        if self._popout_title is not None:
            self._popout_title.configure(text=str(location.get("title", "Map")))
        if self._popout_coordinates is not None:
            self._popout_coordinates.configure(text=self._coordinates_text())
        feature = (
            self._feature_by_id(self._selected_feature_id)
            if self._selected_feature_id is not None
            else None
        )
        if self._popout_feature is not None:
            if feature is None:
                self._popout_feature.configure(
                    text="Hover a marker for details",
                    foreground=COLORS["muted"],
                )
            else:
                status = feature_status(feature, self._completed_feature_ids())
                detail = " ".join(str(feature.get("detail", "")).split())
                if len(detail) > 180:
                    detail = detail[:177] + "..."
                self._popout_feature.configure(
                    text=f"{feature.get('title', 'Feature')} · {status} · {detail}",
                    foreground=COLORS["text"],
                )
        if self._popout_complete_button is not None:
            completed = self._completed_feature_ids()
            if feature is None or not self._feature_is_completable(feature):
                self._popout_complete_button.configure(
                    text="MARK COMPLETE",
                    state="disabled",
                )
            elif feature.get("completed"):
                self._popout_complete_button.configure(
                    text="LOOTED IN GAME",
                    state="disabled",
                )
            else:
                self._popout_complete_button.configure(
                    text=(
                        "MARK INCOMPLETE"
                        if str(feature.get("id", "")) in completed
                        else "MARK COMPLETE"
                    ),
                    state="normal",
                )
        self._draw_map_popout()

    def _draw_map_popout(self) -> None:
        canvas = self._popout_canvas
        if canvas is None or not canvas.winfo_exists():
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        location = self.live.get("location", {})
        image_path = str(location.get("image_path", ""))
        source = self._load_source_image(image_path)
        if source is None:
            scene_key = ("missing", width, height)
            if scene_key != self._popout_scene_key:
                canvas.delete("all")
                self._popout_items = {
                    "message": canvas.create_text(
                        width / 2,
                        height / 2,
                        text="ROM ATLAS IMAGE UNAVAILABLE",
                        fill=COLORS["muted"],
                        font=FONTS["heading"],
                    )
                }
                self._popout_scene_key = scene_key
            return
        metadata = next(
            (
                item
                for item in self.static.get("maps", [])
                if item.get("key") == location.get("map_key")
            ),
            {},
        )
        tile_width = int(metadata.get("tile_width", 16))
        tile_height = int(metadata.get("tile_height", 16))
        player_pixel = (
            (float(location.get("x", 0)) + 0.5) * tile_width,
            (float(location.get("y", 0)) + 0.5) * tile_height,
        )
        scale, (origin_x, origin_y) = map_transform(
            source.size,
            (width, height),
            player_pixel,
            self._popout_zoom,
        )
        resized = (
            max(1, round(source.width * scale)),
            max(1, round(source.height * scale)),
        )
        photo_key = (image_path, *resized)
        if photo_key != self._popout_photo_key:
            display = source.resize(resized, Image.Resampling.NEAREST)
            self._popout_photo = ImageTk.PhotoImage(display)
            self._popout_photo_key = photo_key
        assert self._popout_photo is not None
        features = self.live.get("atlas", {}).get("features", [])
        scene_key = (
            image_path,
            self._source_image_stamp,
            width,
            height,
            resized,
            tuple(
                (
                    str(feature.get("id", "")),
                    feature.get("x"),
                    feature.get("y"),
                    feature.get("kind"),
                )
                for feature in features
            ),
        )
        if scene_key != self._popout_scene_key:
            canvas.delete("all")
            image_item = canvas.create_image(
                origin_x,
                origin_y,
                image=self._popout_photo,
                anchor="nw",
            )
            feature_items: dict[str, int] = {}
            for feature in features:
                feature_id = str(feature.get("id", ""))
                item = canvas.create_oval(0, 0, 0, 0, width=2)
                canvas.tag_bind(
                    item,
                    "<Enter>",
                    lambda event, selected=feature_id: self._show_popout_feature(
                        selected,
                        event,
                    ),
                )
                canvas.tag_bind(
                    item,
                    "<Motion>",
                    lambda event, selected=feature_id: self._show_popout_feature(
                        selected,
                        event,
                    ),
                )
                canvas.tag_bind(item, "<Leave>", lambda _: self._hide_tooltip())
                canvas.tag_bind(
                    item,
                    "<Button-1>",
                    lambda _, selected=feature_id: self._select_feature(selected),
                )
                canvas.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda _, selected=feature_id: self._toggle_feature(selected),
                )
                feature_items[feature_id] = item
            self._popout_items = {
                "image": image_item,
                "features": feature_items,
                "player_outer": canvas.create_oval(0, 0, 0, 0, width=3),
                "player_inner": canvas.create_oval(0, 0, 0, 0, outline=""),
            }
            self._popout_scene_key = scene_key
        canvas.coords(self._popout_items["image"], origin_x, origin_y)
        completed = self._completed_feature_ids()
        feature_items = self._popout_items.get("features", {})
        for feature in features:
            feature_id = str(feature.get("id", ""))
            item = feature_items.get(feature_id)
            if item is None:
                continue
            feature_x = (
                origin_x
                + (float(feature.get("x", 0)) + 0.5) * tile_width * scale
            )
            feature_y = (
                origin_y
                + (float(feature.get("y", 0)) + 0.5) * tile_height * scale
            )
            radius = max(6.0, min(11.0, tile_width * scale * 0.36))
            complete = feature_is_complete(feature, completed)
            canvas.coords(
                item,
                feature_x - radius,
                feature_y - radius,
                feature_x + radius,
                feature_y + radius,
            )
            canvas.itemconfigure(
                item,
                fill=(
                    COLORS["green"]
                    if complete
                    else self._feature_color(str(feature.get("kind", "point")))
                ),
                outline=COLORS["white"] if complete else COLORS["ink"],
            )
        player_x = origin_x + player_pixel[0] * scale
        player_y = origin_y + player_pixel[1] * scale
        radius = max(7.0, min(13.0, tile_width * scale * 0.45))
        canvas.coords(
            self._popout_items["player_outer"],
            player_x - radius,
            player_y - radius,
            player_x + radius,
            player_y + radius,
        )
        canvas.itemconfigure(
            self._popout_items["player_outer"],
            fill=COLORS["white"],
            outline=COLORS["crimson"],
        )
        canvas.coords(
            self._popout_items["player_inner"],
            player_x - 3,
            player_y - 3,
            player_x + 3,
            player_y + 3,
        )
        canvas.itemconfigure(
            self._popout_items["player_inner"],
            fill=COLORS["crimson"],
        )

    def _load_source_image(self, image_path: str) -> Image.Image | None:
        if not image_path:
            return None
        path = Path(image_path)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return None
        if image_path != self._source_image_path or stamp != self._source_image_stamp:
            try:
                with Image.open(path) as image:
                    self._source_image = image.convert("RGB")
            except OSError:
                return None
            self._source_image_path = image_path
            self._source_image_stamp = stamp
            self._map_photo_key = None
            self._popout_photo_key = None
        return self._source_image

    @staticmethod
    def _feature_color(kind: str) -> str:
        return {
            "collectibles": COLORS["gold"],
            "entrance": COLORS["blue"],
            "objective": COLORS["crimson"],
        }.get(kind, COLORS["teal"])

    def _coordinates_text(self) -> str:
        location = self.live.get("location", {})
        return f"X {location.get('x', 0):>3} / Y {location.get('y', 0):>3}"

    def _render_party(self) -> None:
        scroller = ScrollPane(self.workspace_host)
        scroller.pack(fill="both", expand=True)
        page = tk.Frame(scroller.body, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        party = self.live.get("party", [])
        active = [member for member in party if member.get("active")]
        self._page_heading(
            page,
            "The Chosen",
            f"{len(active)} active / {len(party)} recorded companions",
        )
        grid = tk.Frame(page, background=COLORS["ink"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="party")
        grid.grid_columnconfigure(1, weight=1, uniform="party")
        member_widgets: dict[int, dict[str, Any]] = {}
        for index, member in enumerate(active):
            panel = Panel(
                grid,
                str(member.get("name", "Companion")),
                subtitle=f"LEVEL {member.get('level', 0)}",
                accent=(COLORS["teal"], COLORS["gold"], COLORS["crimson"], COLORS["blue"])[index % 4],
            )
            panel.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=(0, 8) if index % 2 == 0 else (8, 0),
                pady=(0, 14),
            )
            hp_label, hp_meter = self._vital(
                panel.body,
                "HP",
                member.get("hp", 0),
                member.get("max_hp", 0),
                COLORS["green"],
            )
            mp_label, mp_meter = self._vital(
                panel.body,
                "MP",
                member.get("mp", 0),
                member.get("max_mp", 0),
                COLORS["blue"],
            )
            status_text, has_condition = self._party_status(member)
            status_label = _label(
                panel.body,
                status_text,
                color=COLORS["crimson"] if has_condition else COLORS["teal"],
                font=FONTS["heading"],
                background=COLORS["surface"],
            )
            status_label.pack(fill="x", pady=(10, 0))
            summary_label = _label(
                panel.body,
                f"Experience {int(member.get('experience', 0)):,} / "
                f"Items {len(member.get('items', []))}",
                color=COLORS["muted"],
                font=FONTS["small"],
                background=COLORS["surface"],
            )
            summary_label.pack(fill="x", pady=(5, 0))
            member_widgets[int(member.get("character_id", index))] = {
                "subtitle": panel.subtitle_label,
                "hp_label": hp_label,
                "hp_meter": hp_meter,
                "mp_label": mp_label,
                "mp_meter": mp_meter,
                "status": status_label,
                "summary": summary_label,
            }
        self._dynamic_widgets["party_members"] = member_widgets
        reserve = Panel(page, "Reserve roster", accent=COLORS["violet"])
        reserve.pack(fill="x")
        inactive = [member for member in party if not member.get("active")]
        _label(
            reserve.body,
            " / ".join(
                f"{member.get('name', 'Companion')} Lv {member.get('level', 0)}"
                for member in inactive
            )
            or "No reserve members detected",
            color=COLORS["muted"],
            background=COLORS["surface"],
            wraplength=760,
        ).pack(fill="x")

    @staticmethod
    def _party_status(member: dict[str, Any]) -> tuple[str, bool]:
        conditions = []
        if not member.get("alive", False):
            conditions.append("DOWN")
        if member.get("poisoned"):
            conditions.append("POISONED")
        if member.get("paralyzed"):
            conditions.append("PARALYZED")
        return (" / ".join(conditions) if conditions else "READY", bool(conditions))

    def _update_party(self) -> None:
        widgets = self._dynamic_widgets.get("party_members", {})
        for member in self.live.get("party", []):
            if not member.get("active"):
                continue
            values = widgets.get(int(member.get("character_id", -1)))
            if values is None:
                continue
            current_hp = int(member.get("hp", 0))
            maximum_hp = int(member.get("max_hp", 0))
            current_mp = int(member.get("mp", 0))
            maximum_mp = int(member.get("max_mp", 0))
            subtitle = values.get("subtitle")
            if subtitle is not None:
                subtitle.configure(text=f"LEVEL {member.get('level', 0)}")
            values["hp_label"].configure(text=f"{current_hp:,} / {maximum_hp:,}")
            values["hp_meter"].set(current_hp / maximum_hp if maximum_hp else 0.0)
            values["mp_label"].configure(text=f"{current_mp:,} / {maximum_mp:,}")
            values["mp_meter"].set(current_mp / maximum_mp if maximum_mp else 0.0)
            status_text, has_condition = self._party_status(member)
            values["status"].configure(
                text=status_text,
                foreground=COLORS["crimson"] if has_condition else COLORS["teal"],
            )
            values["summary"].configure(
                text=(
                    f"Experience {int(member.get('experience', 0)):,} / "
                    f"Items {len(member.get('items', []))}"
                )
            )

    @staticmethod
    def _vital(
        parent: tk.Misc,
        label: str,
        value: int | float | str | None,
        maximum: int | float | str | None,
        color: str,
    ) -> tuple[tk.Label, Meter]:
        current = int(value or 0)
        limit = int(maximum or 0)
        row = tk.Frame(parent, background=COLORS["surface"])
        row.pack(fill="x", pady=(0, 4))
        _label(
            row,
            label,
            color=color,
            font=FONTS["heading"],
            background=COLORS["surface"],
        ).pack(side="left")
        value_label = _label(
            row,
            f"{current:,} / {limit:,}",
            color=COLORS["muted"],
            font=FONTS["small"],
            background=COLORS["surface"],
            anchor="e",
        )
        value_label.pack(side="right")
        meter = Meter(parent, current / limit if limit else 0.0, color=color)
        meter.pack(fill="x", pady=(0, 9))
        return value_label, meter

    def _render_journey(self) -> None:
        scroller = ScrollPane(self.workspace_host)
        scroller.pack(fill="both", expand=True)
        page = tk.Frame(scroller.body, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        journey = self.live.get("journey", {})
        self._page_heading(page, "The Journey", str(journey.get("chapter_name", "Unknown chapter")))
        timeline = tk.Frame(page, background=COLORS["ink"])
        timeline.pack(fill="x", pady=(0, 16))
        chapter = int(journey.get("chapter", 0))
        for index in range(len(self.static.get("chapters", []))):
            segment = tk.Frame(
                timeline,
                background=(
                    COLORS["gold"]
                    if index == chapter
                    else COLORS["teal"]
                    if index < chapter
                    else COLORS["raised"]
                ),
                height=42,
            )
            segment.pack(side="left", fill="x", expand=True, padx=(0, 5) if index < 4 else 0)
            segment.pack_propagate(False)
            _label(
                segment,
                f"CH {index + 1}",
                color=COLORS["ink"] if index <= chapter else COLORS["muted"],
                font=FONTS["heading"],
                background=segment.cget("background"),
                anchor="center",
            ).pack(fill="both", expand=True)

        metrics = tk.Frame(page, background=COLORS["ink"])
        metrics.pack(fill="x", pady=(0, 16))
        metric_widgets: dict[str, tk.Label] = {}
        for label, value, color in (
            ("GOLD", f"{int(journey.get('gold', 0)):,}", COLORS["gold"]),
            ("CASINO", f"{int(journey.get('casino_coins', 0)):,}", COLORS["violet"]),
            ("MEDALS", str(journey.get("small_medals", 0)), COLORS["teal"]),
            ("TREASURE", f"{journey.get('treasure_opened', 0)}/{journey.get('treasure_total', 0)}", COLORS["crimson"]),
        ):
            block = tk.Frame(metrics, background=COLORS["surface"], padx=14, pady=13)
            block.pack(side="left", fill="x", expand=True, padx=(0, 8))
            _label(
                block,
                label,
                color=COLORS["muted"],
                font=FONTS["small"],
                background=COLORS["surface"],
            ).pack(anchor="w")
            value_label = _label(
                block,
                value,
                color=color,
                font=FONTS["metric"],
                background=COLORS["surface"],
            )
            value_label.pack(anchor="w", pady=(3, 0))
            metric_widgets[label.casefold()] = value_label
        self._dynamic_widgets["journey_metrics"] = metric_widgets

        columns = tk.Frame(page, background=COLORS["ink"])
        columns.pack(fill="x")
        columns.grid_columnconfigure(0, weight=1, uniform="journey")
        columns.grid_columnconfigure(1, weight=1, uniform="journey")
        travel = Panel(columns, "Travel state", accent=COLORS["crimson"])
        travel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        travel_widgets: list[tk.Label] = []
        for text, active in self._journey_travel_values(journey):
            widget = _label(
                travel.body,
                ("READY  " if active else "LOCKED  ") + text,
                color=COLORS["teal"] if active else COLORS["muted"],
                background=COLORS["surface"],
            )
            widget.pack(fill="x", pady=3)
            travel_widgets.append(widget)
        self._dynamic_widgets["journey_travel"] = travel_widgets
        returns = Panel(columns, "Return network", accent=COLORS["blue"])
        returns.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        locations = journey.get("return_locations", [])
        return_label = _label(
            returns.body,
            " / ".join(str(value) for value in locations)
            or "No destinations recorded",
            color=COLORS["text"] if locations else COLORS["muted"],
            background=COLORS["surface"],
            wraplength=380,
        )
        return_label.pack(fill="x")
        self._dynamic_widgets["journey_returns"] = return_label

    @staticmethod
    def _journey_travel_values(
        journey: dict[str, Any],
    ) -> tuple[tuple[str, bool], ...]:
        return (
            ("Boat", bool(journey.get("has_boat"))),
            ("Balloon", bool(journey.get("has_balloon"))),
            (str(journey.get("time_name", "Unknown time")), True),
            (f"Tactics: {journey.get('tactics', 'Unknown')}", True),
        )

    def _update_journey(self) -> None:
        journey = self.live.get("journey", {})
        metrics = self._dynamic_widgets.get("journey_metrics", {})
        values = {
            "gold": f"{int(journey.get('gold', 0)):,}",
            "casino": f"{int(journey.get('casino_coins', 0)):,}",
            "medals": str(journey.get("small_medals", 0)),
            "treasure": (
                f"{journey.get('treasure_opened', 0)}/"
                f"{journey.get('treasure_total', 0)}"
            ),
        }
        for key, text in values.items():
            widget = metrics.get(key)
            if widget is not None:
                widget.configure(text=text)
        travel_widgets = self._dynamic_widgets.get("journey_travel", [])
        for widget, (text, active) in zip(
            travel_widgets,
            self._journey_travel_values(journey),
        ):
            widget.configure(
                text=("READY  " if active else "LOCKED  ") + text,
                foreground=COLORS["teal"] if active else COLORS["muted"],
            )
        return_widget = self._dynamic_widgets.get("journey_returns")
        if return_widget is not None:
            locations = journey.get("return_locations", [])
            return_widget.configure(
                text=(
                    " / ".join(str(value) for value in locations)
                    or "No destinations recorded"
                ),
                foreground=COLORS["text"] if locations else COLORS["muted"],
            )

    def _render_journal(self) -> None:
        page = tk.Frame(self.workspace_host, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        self._page_heading(
            page,
            "Dialogue Journal",
            "Previously read dialogue, deduplicated across sessions",
        )
        toolbar = tk.Frame(page, background=COLORS["ink"])
        toolbar.pack(fill="x", pady=(0, 12))
        query = tk.StringVar()
        search = tk.Entry(
            toolbar,
            textvariable=query,
            background=COLORS["raised"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            borderwidth=0,
            highlightbackground=COLORS["line"],
            highlightthickness=1,
            font=FONTS["body"],
        )
        search.pack(side="left", fill="x", expand=True, ipady=7)
        self._dynamic_widgets["journal_count"] = _label(
            toolbar,
            "0 ENTRIES",
            color=COLORS["blue"],
            font=FONTS["heading"],
            background=COLORS["ink"],
            anchor="e",
        )
        self._dynamic_widgets["journal_count"].pack(side="right", padx=(14, 0))

        body = tk.Frame(page, background=COLORS["ink"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2, minsize=360)
        body.grid_columnconfigure(1, weight=3, minsize=420)
        body.grid_rowconfigure(0, weight=1)
        list_panel = Panel(body, "Read history", accent=COLORS["blue"])
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_frame = tk.Frame(list_panel.body, background=COLORS["surface"])
        list_frame.pack(fill="both", expand=True)
        journal_list = tk.Listbox(
            list_frame,
            background=COLORS["surface"],
            foreground=COLORS["text"],
            selectbackground=COLORS["blue"],
            selectforeground=COLORS["ink"],
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=FONTS["body"],
            exportselection=False,
        )
        list_scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=journal_list.yview,
            style="DW.Vertical.TScrollbar",
        )
        journal_list.configure(yscrollcommand=list_scrollbar.set)
        journal_list.pack(side="left", fill="both", expand=True)
        list_scrollbar.pack(side="right", fill="y")
        journal_list.bind("<<ListboxSelect>>", self._select_journal_entry)

        detail_panel = Panel(body, "Journal entry", accent=COLORS["violet"])
        detail_panel.grid(row=0, column=1, sticky="nsew")
        self._dynamic_widgets["journal_title"] = _label(
            detail_panel.body,
            "No dialogue recorded yet",
            color=COLORS["muted"],
            font=FONTS["heading"],
            background=COLORS["surface"],
            wraplength=520,
        )
        self._dynamic_widgets["journal_title"].pack(fill="x")
        self._dynamic_widgets["journal_meta"] = _label(
            detail_panel.body,
            "",
            color=COLORS["blue"],
            font=FONTS["small"],
            background=COLORS["surface"],
            wraplength=520,
        )
        self._dynamic_widgets["journal_meta"].pack(fill="x", pady=(7, 0))
        tk.Frame(
            detail_panel.body,
            background=COLORS["line_soft"],
            height=1,
        ).pack(fill="x", pady=14)
        self._dynamic_widgets["journal_text"] = _label(
            detail_panel.body,
            "Dialogue will appear here after it has finished drawing in game.",
            color=COLORS["muted"],
            font=FONTS["body"],
            background=COLORS["surface"],
            anchor="nw",
            wraplength=520,
        )
        self._dynamic_widgets["journal_text"].pack(fill="both", expand=True)
        self._dynamic_widgets["journal_query"] = query
        self._dynamic_widgets["journal_list"] = journal_list
        self._dynamic_widgets["journal_entry_ids"] = []
        self._dynamic_widgets["journal_rows_key"] = ()
        query.trace_add("write", lambda *_: self._update_journal())
        self._update_journal()

    def _journal_entries(self) -> list[dict[str, Any]]:
        values = [
            entry
            for entry in self.live.get("journal", [])
            if isinstance(entry, dict)
        ]
        query_value = self._dynamic_widgets.get("journal_query")
        query = (
            str(query_value.get()).strip().casefold()
            if isinstance(query_value, tk.StringVar)
            else ""
        )
        if query:
            values = [
                entry
                for entry in values
                if query
                in f"{entry.get('location', '')} {entry.get('text', '')}".casefold()
            ]
        return list(reversed(values))

    def _select_journal_entry(self, _: tk.Event | None = None) -> None:
        journal_list = self._dynamic_widgets.get("journal_list")
        entry_ids = self._dynamic_widgets.get("journal_entry_ids", [])
        if not isinstance(journal_list, tk.Listbox):
            return
        selection = journal_list.curselection()
        if selection and selection[0] < len(entry_ids):
            self._dynamic_widgets["selected_journal_id"] = entry_ids[selection[0]]
        self._update_journal_detail()

    def _update_journal(self) -> None:
        journal_list = self._dynamic_widgets.get("journal_list")
        if not isinstance(journal_list, tk.Listbox):
            return
        entries = self._journal_entries()
        rows_key = tuple(
            (
                str(entry.get("entry_id", "")),
                str(entry.get("location", "")),
                str(entry.get("text", "")),
                int(entry.get("seen_count", 1)),
            )
            for entry in entries
        )
        selected_id = self._dynamic_widgets.get("selected_journal_id")
        if rows_key != self._dynamic_widgets.get("journal_rows_key"):
            journal_list.delete(0, "end")
            for entry in entries:
                text = " ".join(str(entry.get("text", "")).split())
                preview = text if len(text) <= 58 else text[:55] + "..."
                seen = int(entry.get("seen_count", 1))
                suffix = f"  x{seen}" if seen > 1 else ""
                journal_list.insert(
                    "end",
                    f"{entry.get('location', 'Unknown')}  |  {preview}{suffix}",
                )
            entry_ids = [str(entry.get("entry_id", "")) for entry in entries]
            self._dynamic_widgets["journal_entry_ids"] = entry_ids
            self._dynamic_widgets["journal_rows_key"] = rows_key
            if selected_id not in entry_ids:
                selected_id = entry_ids[0] if entry_ids else None
                self._dynamic_widgets["selected_journal_id"] = selected_id
            if selected_id in entry_ids:
                index = entry_ids.index(selected_id)
                journal_list.selection_clear(0, "end")
                journal_list.selection_set(index)
                journal_list.see(index)
        count = self._dynamic_widgets.get("journal_count")
        if count is not None:
            total = len(self.live.get("journal", []))
            count.configure(text=f"{total} {'ENTRY' if total == 1 else 'ENTRIES'}")
        self._update_journal_detail()

    def _update_journal_detail(self) -> None:
        selected_id = self._dynamic_widgets.get("selected_journal_id")
        entry = next(
            (
                value
                for value in self.live.get("journal", [])
                if isinstance(value, dict)
                and str(value.get("entry_id", "")) == selected_id
            ),
            None,
        )
        title = self._dynamic_widgets.get("journal_title")
        meta = self._dynamic_widgets.get("journal_meta")
        text = self._dynamic_widgets.get("journal_text")
        if not isinstance(title, tk.Label):
            return
        if not isinstance(meta, tk.Label):
            return
        if not isinstance(text, tk.Label):
            return
        if entry is None:
            title.configure(text="No dialogue recorded yet", foreground=COLORS["muted"])
            meta.configure(text="")
            text.configure(
                text="Dialogue will appear here after it has finished drawing in game.",
                foreground=COLORS["muted"],
            )
            return
        title.configure(text=str(entry.get("location", "Unknown location")), foreground=COLORS["text"])
        first_seen = self._journal_time(str(entry.get("first_seen", "")))
        last_seen = self._journal_time(str(entry.get("last_seen", "")))
        seen_count = int(entry.get("seen_count", 1))
        meta.configure(
            text=(
                f"First read {first_seen}  |  Last read {last_seen}  |  "
                f"Seen {seen_count} {'time' if seen_count == 1 else 'times'}"
            )
        )
        text.configure(text=str(entry.get("text", "")), foreground=COLORS["text"])

    @staticmethod
    def _journal_time(value: str) -> str:
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value or "unknown"

    def _render_encounters(self) -> None:
        page = tk.Frame(self.workspace_host, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        self._page_heading(
            page,
            "Combat Log",
            "Fast-captured battle flow / one JSON per completed combat",
        )
        active_panel = Panel(page, "Live encounter", accent=COLORS["crimson"])
        active_panel.pack(fill="x", pady=(0, 12))
        active_row = tk.Frame(active_panel.body, background=COLORS["surface"])
        active_row.pack(fill="x")
        self._dynamic_widgets["combat_active_status"] = _label(
            active_row,
            "IDLE",
            color=COLORS["muted"],
            font=FONTS["metric"],
            background=COLORS["surface"],
        )
        self._dynamic_widgets["combat_active_status"].pack(side="left")
        self._dynamic_widgets["combat_active_summary"] = _label(
            active_row,
            "Waiting for coherent enemy slots",
            color=COLORS["muted"],
            background=COLORS["surface"],
            anchor="e",
            justify="right",
            wraplength=720,
        )
        self._dynamic_widgets["combat_active_summary"].pack(
            side="right",
            fill="x",
            expand=True,
            padx=(18, 0),
        )

        body = tk.Frame(page, background=COLORS["ink"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2, minsize=360)
        body.grid_columnconfigure(1, weight=3, minsize=460)
        body.grid_rowconfigure(0, weight=1)
        list_panel = Panel(body, "Completed encounters", accent=COLORS["gold"])
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_frame = tk.Frame(list_panel.body, background=COLORS["surface"])
        list_frame.pack(fill="both", expand=True)
        encounter_list = tk.Listbox(
            list_frame,
            background=COLORS["surface"],
            foreground=COLORS["text"],
            selectbackground=COLORS["crimson"],
            selectforeground=COLORS["white"],
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=FONTS["body"],
            exportselection=False,
        )
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=encounter_list.yview,
            style="DW.Vertical.TScrollbar",
        )
        encounter_list.configure(yscrollcommand=scrollbar.set)
        encounter_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        encounter_list.bind("<<ListboxSelect>>", self._select_encounter)

        detail_panel = Panel(body, "Combat result", accent=COLORS["teal"])
        detail_panel.grid(row=0, column=1, sticky="nsew")
        self._dynamic_widgets["encounter_title"] = _label(
            detail_panel.body,
            "No completed encounters",
            color=COLORS["muted"],
            font=FONTS["heading"],
            background=COLORS["surface"],
            wraplength=560,
        )
        self._dynamic_widgets["encounter_title"].pack(fill="x")
        self._dynamic_widgets["encounter_meta"] = _label(
            detail_panel.body,
            "",
            color=COLORS["teal"],
            font=FONTS["small"],
            background=COLORS["surface"],
            wraplength=560,
        )
        self._dynamic_widgets["encounter_meta"].pack(fill="x", pady=(6, 10))
        encounter_detail = tk.Text(
            detail_panel.body,
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=FONTS["body"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
            padx=0,
            pady=0,
        )
        encounter_detail.pack(fill="both", expand=True)
        self._dynamic_widgets["encounter_list"] = encounter_list
        self._dynamic_widgets["encounter_ids"] = []
        self._dynamic_widgets["encounter_rows_key"] = ()
        self._dynamic_widgets["encounter_cache"] = {}
        self._dynamic_widgets["encounter_detail"] = encounter_detail
        self._update_encounters()

    def _select_encounter(self, _: tk.Event | None = None) -> None:
        encounter_list = self._dynamic_widgets.get("encounter_list")
        encounter_ids = self._dynamic_widgets.get("encounter_ids", [])
        if not isinstance(encounter_list, tk.Listbox):
            return
        selection = encounter_list.curselection()
        if selection and selection[0] < len(encounter_ids):
            self._dynamic_widgets["selected_encounter_id"] = encounter_ids[
                selection[0]
            ]
        self._update_encounter_detail()

    def _update_encounters(self) -> None:
        combat = self.live.get("combat", {})
        active = combat.get("active")
        status = self._dynamic_widgets.get("combat_active_status")
        summary = self._dynamic_widgets.get("combat_active_summary")
        if isinstance(status, tk.Label) and isinstance(summary, tk.Label):
            if isinstance(active, dict):
                enemies = ", ".join(
                    f"{enemy.get('label', 'Enemy')} HP {enemy.get('final_hp', 0)}"
                    for enemy in active.get("enemies", [])
                ) or "Enemy identity pending"
                status.configure(text="CAPTURING", foreground=COLORS["crimson"])
                summary.configure(
                    text=(
                        f"{active.get('location', 'Unknown')}  |  "
                        f"{active.get('frame_count', 0)} distinct frames  |  "
                        f"{enemies}"
                    ),
                    foreground=COLORS["text"],
                )
            elif not combat.get("memory_available", False):
                status.configure(text="UNAVAILABLE", foreground=COLORS["crimson"])
                summary.configure(
                    text=str(
                        combat.get("detector_evidence", "Battle memory unavailable")
                    ),
                    foreground=COLORS["muted"],
                )
            else:
                status.configure(text="IDLE", foreground=COLORS["muted"])
                summary.configure(
                    text="Waiting for coherent enemy slots",
                    foreground=COLORS["muted"],
                )

        encounter_list = self._dynamic_widgets.get("encounter_list")
        if not isinstance(encounter_list, tk.Listbox):
            return
        recent = [
            value
            for value in combat.get("recent", [])
            if isinstance(value, dict)
        ]
        rows_key = tuple(
            (
                str(value.get("encounter_id", "")),
                str(value.get("outcome", "")),
                str(value.get("end_location", "")),
            )
            for value in recent
        )
        selected_id = self._dynamic_widgets.get("selected_encounter_id")
        if rows_key != self._dynamic_widgets.get("encounter_rows_key"):
            encounter_list.delete(0, "end")
            for value in recent:
                outcome = str(value.get("outcome", "unknown")).replace("_", " ").upper()
                enemies = ", ".join(
                    str(label) for label in value.get("enemy_labels", [])
                ) or "Unknown enemies"
                encounter_list.insert(
                    "end",
                    f"{outcome}  |  {value.get('end_location', 'Unknown')}  |  {enemies}",
                )
            encounter_ids = [
                str(value.get("encounter_id", "")) for value in recent
            ]
            self._dynamic_widgets["encounter_ids"] = encounter_ids
            self._dynamic_widgets["encounter_rows_key"] = rows_key
            if selected_id not in encounter_ids:
                selected_id = encounter_ids[0] if encounter_ids else None
                self._dynamic_widgets["selected_encounter_id"] = selected_id
            if selected_id in encounter_ids:
                index = encounter_ids.index(selected_id)
                encounter_list.selection_clear(0, "end")
                encounter_list.selection_set(index)
                encounter_list.see(index)
        self._update_encounter_detail()

    def _update_encounter_detail(self) -> None:
        selected_id = self._dynamic_widgets.get("selected_encounter_id")
        summary = next(
            (
                value
                for value in self.live.get("combat", {}).get("recent", [])
                if isinstance(value, dict)
                and str(value.get("encounter_id", "")) == selected_id
            ),
            None,
        )
        title = self._dynamic_widgets.get("encounter_title")
        meta = self._dynamic_widgets.get("encounter_meta")
        detail = self._dynamic_widgets.get("encounter_detail")
        if not isinstance(title, tk.Label):
            return
        if not isinstance(meta, tk.Label):
            return
        if not isinstance(detail, tk.Text):
            return
        if summary is None:
            title.configure(text="No completed encounters", foreground=COLORS["muted"])
            meta.configure(text="")
            self._set_text(detail, "Completed combat records will appear here.")
            return
        record = self._load_encounter_record(summary)
        outcome = str(record.get("outcome", "unknown")).replace("_", " ").upper()
        title.configure(
            text=f"{outcome} · {record.get('end_location', 'Unknown')}",
            foreground=self._outcome_color(str(record.get("outcome", ""))),
        )
        meta.configure(
            text=(
                f"{self._journal_time(str(record.get('ended_at', '')))}  |  "
                f"{float(record.get('duration_seconds', 0)):.2f}s  |  "
                f"{int(record.get('sample_count', 0))} distinct frames  |  "
                f"{record.get('encounter_id', '')}"
            )
        )
        lines = [
            f"Rewards: {int(record.get('reward_experience', 0)):,} XP / "
            f"{int(record.get('reward_gold', 0)):,} gold",
            f"Observed persistent gains: {int(record.get('observed_experience_gain', 0)):,} XP / "
            f"{int(record.get('observed_gold_gain', 0)):,} gold",
            "",
            "Enemies",
        ]
        enemies = record.get("enemies", [])
        if enemies:
            lines.extend(
                f"{enemy.get('label', 'Enemy')}: HP "
                f"{enemy.get('starting_hp', 0)} → {enemy.get('final_hp', 0)} "
                f"(lowest {enemy.get('lowest_hp', 0)}), ATK {enemy.get('attack', 0)}, "
                f"DEF {enemy.get('defense', 0)}, AGI {enemy.get('agility', 0)}"
                for enemy in enemies
            )
        else:
            lines.append("Enemy frames were skipped; record reconstructed from rewards.")
        lines.extend(("", "Party result"))
        start_party = {
            int(value.get("character_id", -1)): value
            for value in record.get("party_start", [])
        }
        for member in record.get("party_end", []):
            starting = start_party.get(int(member.get("character_id", -1)), {})
            lines.append(
                f"{member.get('name', 'Party member')}: HP "
                f"{starting.get('hp', '?')} → {member.get('hp', '?')}, MP "
                f"{starting.get('mp', '?')} → {member.get('mp', '?')}"
            )
        evidence = record.get("outcome_evidence", [])
        if evidence:
            lines.extend(("", "Result evidence", *(str(value) for value in evidence)))
        lines.extend(
            (
                "",
                "Capture evidence",
                str(record.get("detector_evidence", "")),
            )
        )
        self._set_text(detail, "\n".join(lines))

    def _load_encounter_record(self, summary: dict[str, Any]) -> dict[str, Any]:
        encounter_id = str(summary.get("encounter_id", ""))
        cache = self._dynamic_widgets.get("encounter_cache", {})
        if encounter_id in cache:
            return cache[encounter_id]
        try:
            ended_at = datetime.fromisoformat(str(summary.get("ended_at", "")))
            path = (
                self.state_dir.parent
                / "encounters"
                / f"{ended_at.year:04d}"
                / f"{ended_at.month:02d}"
                / f"{ended_at.day:02d}"
                / f"{encounter_id}.json"
            )
            record = _read_json(path, summary)
        except ValueError:
            record = summary
        cache[encounter_id] = record
        self._dynamic_widgets["encounter_cache"] = cache
        return record

    @staticmethod
    def _outcome_color(outcome: str) -> str:
        return {
            "victory": COLORS["green"],
            "defeat": COLORS["crimson"],
            "escaped_or_interrupted": COLORS["gold"],
        }.get(outcome, COLORS["muted"])

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _render_archive(self) -> None:
        scroller = ScrollPane(self.workspace_host)
        scroller.pack(fill="both", expand=True)
        page = tk.Frame(scroller.body, background=COLORS["ink"], padx=22, pady=20)
        page.pack(fill="both", expand=True)
        reference = self.live.get("reference", {})
        self._page_heading(
            page,
            "Research Archive",
            f"{reference.get('saved_pages', 0)}/{reference.get('total_pages', 0)} saved references available",
        )
        confidence = Panel(page, "Active evidence", accent=COLORS["gold"])
        confidence.pack(fill="x", pady=(0, 14))
        for label, value, color in (
            ("LIVE MEMORY", reference.get("memory_region", "Unknown"), COLORS["teal"]),
            ("ROM LAYOUT", reference.get("rom_region", "Unavailable"), COLORS["gold"]),
            ("LOCATION SOURCE", reference.get("evidence", "Unknown"), COLORS["muted"]),
        ):
            row = tk.Frame(confidence.body, background=COLORS["surface"])
            row.pack(fill="x", pady=3)
            _label(
                row,
                label,
                color=COLORS["muted"],
                font=FONTS["small"],
                background=COLORS["surface"],
            ).pack(side="left")
            _label(
                row,
                str(value),
                color=color,
                background=COLORS["surface"],
                anchor="e",
                wraplength=650,
            ).pack(side="right", fill="x", expand=True)

        source_panel = Panel(page, "Saved pages", accent=COLORS["violet"])
        source_panel.pack(fill="x", pady=(0, 14))
        for source in self.static.get("sources", []):
            row = tk.Frame(source_panel.body, background=COLORS["surface"])
            row.pack(fill="x", pady=5)
            tk.Frame(
                row,
                width=4,
                background=COLORS["teal"] if source.get("available") else COLORS["crimson"],
            ).pack(side="left", fill="y")
            text = tk.Frame(row, background=COLORS["surface"])
            text.pack(side="left", fill="x", expand=True, padx=(10, 12))
            _label(
                text,
                str(source.get("title", "Reference")),
                font=FONTS["heading"],
                background=COLORS["surface"],
            ).pack(fill="x")
            _label(
                text,
                str(source.get("purpose", "")),
                color=COLORS["muted"],
                font=FONTS["small"],
                background=COLORS["surface"],
                wraplength=680,
            ).pack(fill="x", pady=(2, 0))
            url = str(source.get("url", ""))
            _button(
                row,
                "OPEN",
                lambda target=url: _open_url(target),
                accent=COLORS["violet"],
                width=6,
            ).pack(side="right")

        legend = Panel(page, "Tile behavior legend", accent=COLORS["teal"])
        legend.pack(fill="x")
        values = self.static.get("tile_behaviors", [])
        columns = [values[index::3] for index in range(3)]
        for index, entries in enumerate(columns):
            column = tk.Frame(legend.body, background=COLORS["surface"])
            column.pack(side="left", fill="x", expand=True, padx=(0, 12) if index < 2 else 0)
            for entry in entries:
                _label(
                    column,
                    f"${int(entry.get('value', 0)):02X}  {entry.get('name', '')}",
                    color=COLORS["muted"],
                    font=FONTS["small"],
                    background=COLORS["surface"],
                ).pack(fill="x", pady=2)

    def _poll(self) -> None:
        try:
            stamp = self.live_path.stat().st_mtime_ns
        except OSError:
            self.connection_label.configure(text="WAITING", foreground=COLORS["crimson"])
        else:
            if stamp != self._live_stamp:
                document = _read_json(self.live_path, {})
                if document:
                    self.live = document
                    self._live_stamp = stamp
                    self._on_live_update()
            self.connection_label.configure(text="LIVE", foreground=COLORS["teal"])
        self.root.after(250, self._poll)

    def _on_live_update(self) -> None:
        location = self.live.get("location", {})
        self.location_label.configure(text=str(location.get("title", "Waiting for game")))
        mode = str(self.live.get("mode", "waiting")).upper()
        self.mode_label.configure(text=mode)
        reference = self.live.get("reference", {})
        self.source_label.configure(
            text=(
                f"Memory: {reference.get('memory_region', '--')} / "
                f"ROM: {reference.get('rom_region', '--')}"
            )
        )
        self._update_map_popout()
        signature = workspace_render_signature(self.workspace, self.live)
        if signature != self._render_signature:
            self._render_workspace()
        else:
            self._update_dynamic_workspace()

    def _update_dynamic_workspace(self) -> None:
        if self.workspace == "atlas":
            self._update_atlas()
        elif self.workspace == "party":
            self._update_party()
        elif self.workspace == "journey":
            self._update_journey()
        elif self.workspace == "journal":
            self._update_journal()
        elif self.workspace == "encounters":
            self._update_encounters()

    def _close(self) -> None:
        self.controls["dashboard_open"] = False
        _write_json(self.controls_path, self.controls)
        self._close_map_popout()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dragon Warrior IV companion dashboard")
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    CompanionDashboard(args.state_dir).run()


if __name__ == "__main__":
    main()