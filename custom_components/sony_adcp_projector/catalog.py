"""Catalog of ADCP commands this integration knows how to present.

Sony does not publish one command list per model, and command names differ
between business (VPL-FHZ…) and home-cinema/simulation models (VPL-VW/XW/GTZ).
Instead of hard-coding a model table, every candidate below is *probed* on the
projector with ``<command> --info``. Only commands the projector answers become
entities, using the ranges and choices the projector itself reports. Wrong or
outdated names are harmless: they are recorded as unsupported and skipped.

The menu groupings follow the VPL-GTZ380 help guide (Picture, Screen,
Function, Setup and Installation menus).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import EntityCategory

# Commands handled by dedicated entities/code; never generic.
RESERVED_COMMANDS = frozenset(
    {
        "power",
        "power_status",
        "input",
        "error",
        "warning",
        "timer",
        "version",
        "modelname",
        "serialnum",
        "mac_address",
        "signal",
        "key",
    }
)


@dataclass(frozen=True, kw_only=True, slots=True)
class Feature:
    """One probe-able ADCP command."""

    command: str
    suffix: str | None = None
    translation_key: str | None = None
    entity_category: EntityCategory | None = None
    enabled_default: bool = True
    # Values are queried on every refresh while the projector is on.
    poll: bool = True

    @property
    def key(self) -> str:
        """Stable identifier, also used in unique IDs."""
        if self.suffix:
            return f"{self.command}_{self.suffix.removeprefix('--')}"
        return self.command

    @property
    def tkey(self) -> str | None:
        return self.translation_key or None


_CFG = EntityCategory.CONFIG


def _f(command: str, **kwargs: object) -> Feature:
    kwargs.setdefault("translation_key", command)
    return Feature(command=command, **kwargs)  # type: ignore[arg-type]


def _suffixed(
    command: str, suffixes: tuple[str, ...], translation_key: str, **kwargs: object
) -> list[Feature]:
    return [
        Feature(
            command=command,
            suffix=f"--{suffix}",
            translation_key=f"{translation_key}_{suffix}",
            **kwargs,  # type: ignore[arg-type]
        )
        for suffix in suffixes
    ]


_RGB = ("r", "g", "b")
_SIX = ("r", "y", "g", "c", "b", "m")
_EDGES = ("top", "bottom", "left", "right")

FEATURES: tuple[Feature, ...] = (
    # ---- Basic operation -------------------------------------------------
    _f("blank"),  # Picture muting
    _f("freeze"),
    _f("muting"),
    _f("volume"),
    # ---- Picture menu ------------------------------------------------------
    _f("picture_mode"),  # "Calib. Preset" on the GTZ380
    _f("picture_mode_reset", entity_category=_CFG, enabled_default=False, poll=False),
    _f("real_cre"),
    _f("real_cre_reso"),
    _f("real_cre_noise"),
    # Cinema Black Pro → Laser Light Setting / Dynamic Control
    _f("light_output_mode"),
    _f("light_output_val"),
    _f("light_output_dyn"),
    _f("dyn_light_ctrl"),
    _f("laser_dyn_ctrl"),
    # Cinema Black Pro → Dynamic HDR Enhancer / D.Contrast Optimizer
    _f("dyn_hdr_enhancer"),
    _f("hdr_dyn_tone_map"),
    _f("contrast_enh"),
    _f("d_contrast_opt"),
    _f("motionflow"),
    _f("contrast"),
    _f("brightness"),
    _f("color"),
    _f("hue"),
    _f("color_temp"),
    _f("sharpness"),
    # Expert settings
    _f("nr"),
    _f("mpeg_nr"),
    _f("smooth_gradation"),
    _f("smooth_grad"),
    _f("film_mode"),
    _f("gamma_correction"),
    _f("black_level_adj"),
    _f("hdr"),
    _f("hdr_contrast"),
    _f("color_space"),
    _f("input_lag_red"),
    _f("input_lag_reduction"),
    _f("clear_white"),
    _f("x_vivid"),
    # Custom colour temperature (Gain / Bias)
    *(
        _f(f"coltemp_{kind}_{ch}", entity_category=_CFG, enabled_default=False)
        for kind in ("gain", "bias")
        for ch in _RGB
    ),
    # Colour correction
    _f("col_correction", entity_category=_CFG),
    *_suffixed("col_corr_hue", _SIX, "col_corr_hue", entity_category=_CFG, enabled_default=False),
    *_suffixed(
        "col_corr_color", _SIX, "col_corr_color", entity_category=_CFG, enabled_default=False
    ),
    *_suffixed("col_corr_brt", _SIX, "col_corr_brt", entity_category=_CFG, enabled_default=False),
    # ---- Screen menu -----------------------------------------------------------
    _f("aspect"),
    _f("pic_pos_sel"),  # Picture Position (lens memory) recall
    _f("pic_pos_save", entity_category=_CFG, poll=False),
    _f("pic_pos_del", entity_category=_CFG, enabled_default=False, poll=False),
    *_suffixed("blanking", _EDGES, "blanking", entity_category=_CFG, enabled_default=False),
    _f("overscan", entity_category=_CFG),
    # ---- Function menu ------------------------------------------------------
    _f("2d3d_sel"),
    _f("3d_format"),
    _f("3d_brightness"),
    _f("3d_depth"),
    _f("dynamic_range", entity_category=_CFG),
    *_suffixed(
        "dynamic_range",
        ("hdmi1", "hdmi2"),
        "dynamic_range",
        entity_category=_CFG,
        enabled_default=False,
    ),
    _f("hdmi_signal_format", entity_category=_CFG, enabled_default=False),
    _f("test_pattern"),
    _f("settings_lock", entity_category=_CFG, enabled_default=False),
    _f("setting_lock", entity_category=_CFG, enabled_default=False),  # VPL-GTZ380
    # ---- Setup menu -------------------------------------------------------
    _f("high_alt_mode", entity_category=_CFG, enabled_default=False),
    _f("remote_start", entity_category=_CFG, enabled_default=False),
    _f("network_management", entity_category=_CFG, enabled_default=False),
    _f("standby_mode", entity_category=_CFG, enabled_default=False),
    _f("powsave_nosig", entity_category=_CFG, enabled_default=False),
    _f("language", entity_category=_CFG, enabled_default=False),
    _f("menu_pos", entity_category=_CFG, enabled_default=False),
    _f("status_disp", entity_category=_CFG, enabled_default=False),
    # ---- Installation menu ------------------------------------------------
    _f("image_flip", entity_category=_CFG, enabled_default=False),
    _f("anamorphic_lens", entity_category=_CFG),
    _f("trigger", entity_category=_CFG, enabled_default=False),
    _f("ir_receiver", entity_category=_CFG, enabled_default=False),
    _f("infrared", entity_category=_CFG, enabled_default=False),  # VPL-GTZ380
    _f("lens_lock", entity_category=_CFG, enabled_default=False),
    _f("controlkey_lock", entity_category=_CFG, enabled_default=False),
    _f("panel_alignment", entity_category=_CFG, enabled_default=False),
)

FEATURES_BY_KEY: dict[str, Feature] = {feature.key: feature for feature in FEATURES}


def extra_feature(spec: str) -> Feature | None:
    """Turn a user-supplied ``command`` or ``command --suffix`` into a Feature."""
    parts = spec.strip().split()
    if not parts or len(parts) > 2:
        return None
    command, suffix = parts[0].lower(), (parts[1].lower() if len(parts) == 2 else None)
    if command in RESERVED_COMMANDS:
        return None
    if not command.replace("_", "").isalnum() or not command.isascii():
        return None
    if suffix is not None and (
        not suffix.startswith("--") or not suffix[2:].replace("_", "").isalnum()
    ):
        return None
    return Feature(command=command, suffix=suffix, translation_key=None)


# Remote-control key codes exposed as buttons (lens motors cannot be queried,
# so these are always created; keys the model lacks simply return an error).
LENS_KEYS: tuple[str, ...] = (
    "lens_focus_far",
    "lens_focus_near",
    "lens_zoom_up",
    "lens_zoom_down",
    "lens_shift_up",
    "lens_shift_down",
    "lens_shift_left",
    "lens_shift_right",
)

MENU_KEYS: tuple[str, ...] = (
    "menu",
    "up",
    "down",
    "left",
    "right",
    "enter",
    "return",
    "reset",
)

# Documented key codes, used for remote.send_command validation hints.
KNOWN_KEYS: frozenset[str] = frozenset(
    {
        *LENS_KEYS,
        *MENU_KEYS,
        "power",
        "power_on",
        "power_off",
        "input",
        "blank",
        "picmode",
        "picture+",
        "picture_",
        "bright+",
        "bright_",
        "color+",
        "color_",
        "hue+",
        "hue_",
        "sharpness+",
        "sharpness_",
        "color_temp",
        "aspect",
        "pattern",
        "freeze",
        "lens_control",
        "lens_focus",
        "lens_zoom",
        "lens_shift",
        "lens_position",
        "status_on",
        "status_off",
    }
)
