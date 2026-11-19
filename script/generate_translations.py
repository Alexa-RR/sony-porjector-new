"""Generate translations/en.json and icons.json from one source of truth.

Which platform an ADCP feature lands on (select, switch, number, button,
sensor) is decided at runtime from the projector's ``--info`` reply, so every
feature name is emitted for each platform it can plausibly appear on.

Run:  python script/generate_translations.py          (write files)
      python script/generate_translations.py --check  (CI: fail if stale)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "sony_adcp_projector"

_RGB = {"r": "red", "g": "green", "b": "blue"}
_SIX = {"r": "red", "y": "yellow", "g": "green", "c": "cyan", "b": "blue", "m": "magenta"}

# feature translation_key -> (English name, icon)
FEATURE_NAMES: dict[str, tuple[str, str]] = {
    "blank": ("Picture muting", "mdi:projector-off"),
    "freeze": ("Freeze", "mdi:pause-box"),
    "muting": ("Audio muting", "mdi:volume-off"),
    "volume": ("Volume", "mdi:volume-high"),
    "picture_mode": ("Calib. preset", "mdi:palette"),
    "picture_mode_reset": ("Reset picture adjustments", "mdi:restore"),
    "real_cre": ("Reality Creation", "mdi:auto-fix"),
    "real_cre_reso": ("Reality Creation resolution", "mdi:image-filter-hdr"),
    "real_cre_noise": ("Reality Creation noise filtering", "mdi:blur"),
    "light_output_mode": ("Laser light mode", "mdi:brightness-6"),
    "light_output_val": ("Laser light output", "mdi:brightness-percent"),
    "light_output_dyn": ("Dynamic laser control", "mdi:brightness-auto"),
    "dyn_light_ctrl": ("Dynamic light control", "mdi:brightness-auto"),
    "laser_dyn_ctrl": ("Laser dynamic control", "mdi:brightness-auto"),
    "dyn_hdr_enhancer": ("Dynamic HDR Enhancer", "mdi:hdr"),
    "hdr_dyn_tone_map": ("HDR dynamic tone mapping", "mdi:hdr"),
    "contrast_enh": ("Contrast enhancer", "mdi:contrast-box"),
    "d_contrast_opt": ("D.Contrast Optimizer", "mdi:contrast-box"),
    "motionflow": ("Motionflow", "mdi:motion-play"),
    "contrast": ("Contrast", "mdi:contrast-circle"),
    "brightness": ("Brightness", "mdi:brightness-5"),
    "color": ("Color", "mdi:palette-swatch"),
    "hue": ("Hue", "mdi:looks"),
    "color_temp": ("Color temperature", "mdi:thermometer"),
    "sharpness": ("Sharpness", "mdi:image-filter-center-focus"),
    "nr": ("Noise reduction", "mdi:blur-linear"),
    "mpeg_nr": ("MPEG noise reduction", "mdi:blur-linear"),
    "smooth_gradation": ("Smooth gradation", "mdi:gradient-horizontal"),
    "smooth_grad": ("Smooth gradation", "mdi:gradient-horizontal"),
    "film_mode": ("Film mode", "mdi:filmstrip"),
    "gamma_correction": ("Gamma correction", "mdi:chart-bell-curve-cumulative"),
    "black_level_adj": ("Black level", "mdi:invert-colors"),
    "hdr": ("HDR", "mdi:hdr"),
    "hdr_contrast": ("HDR contrast", "mdi:hdr"),
    "color_space": ("Color space", "mdi:palette-advanced"),
    "input_lag_red": ("Input lag reduction", "mdi:gamepad-variant"),
    "input_lag_reduction": ("Input lag reduction", "mdi:gamepad-variant"),
    "clear_white": ("Clear White", "mdi:white-balance-sunny"),
    "x_vivid": ("x.v.Color", "mdi:palette"),
    **{
        f"coltemp_{kind}_{ch}": (
            f"Color temperature {kind} {name}",
            "mdi:tune-vertical",
        )
        for kind in ("gain", "bias")
        for ch, name in _RGB.items()
    },
    "col_correction": ("Color correction", "mdi:palette-swatch-variant"),
    **{
        f"col_corr_{kind}_{ch}": (
            f"Color correction {label} {name}",
            "mdi:tune-variant",
        )
        for kind, label in (("hue", "hue"), ("color", "color"), ("brt", "brightness"))
        for ch, name in _SIX.items()
    },
    "aspect": ("Aspect", "mdi:aspect-ratio"),
    "pic_pos_sel": ("Picture position", "mdi:projector-screen"),
    "pic_pos_save": ("Save picture position {choice}", "mdi:content-save"),
    "pic_pos_del": ("Delete picture position {choice}", "mdi:delete"),
    **{
        f"blanking_{edge}": (f"Blanking {edge}", "mdi:border-outside")
        for edge in ("top", "bottom", "left", "right")
    },
    "overscan": ("Overscan", "mdi:fit-to-screen"),
    "2d3d_sel": ("2D/3D display", "mdi:video-3d"),
    "3d_format": ("3D format", "mdi:video-3d"),
    "3d_brightness": ("3D brightness", "mdi:video-3d"),
    "3d_depth": ("3D depth", "mdi:video-3d"),
    "dynamic_range": ("Dynamic range", "mdi:arrow-expand-horizontal"),
    "dynamic_range_hdmi1": ("Dynamic range HDMI 1", "mdi:arrow-expand-horizontal"),
    "dynamic_range_hdmi2": ("Dynamic range HDMI 2", "mdi:arrow-expand-horizontal"),
    "hdmi_signal_format": ("HDMI signal format", "mdi:hdmi-port"),
    "test_pattern": ("Test pattern", "mdi:grid"),
    "settings_lock": ("Settings lock", "mdi:lock"),
    "high_alt_mode": ("High altitude mode", "mdi:image-filter-hdr"),
    "remote_start": ("Remote start", "mdi:remote"),
    "network_management": ("Network management", "mdi:lan"),
    "standby_mode": ("Standby mode", "mdi:power-sleep"),
    "powsave_nosig": ("Power saving", "mdi:leaf"),
    "language": ("Menu language", "mdi:translate"),
    "menu_pos": ("Menu position", "mdi:page-layout-sidebar-left"),
    "status_disp": ("On-screen status display", "mdi:message-text"),
    "image_flip": ("Image flip", "mdi:flip-horizontal"),
    "anamorphic_lens": ("Anamorphic lens", "mdi:panorama-horizontal"),
    "trigger": ("Trigger", "mdi:electric-switch"),
    "ir_receiver": ("IR receiver", "mdi:remote"),
    "lens_lock": ("Lens control lock", "mdi:lock"),
    "controlkey_lock": ("Control key lock", "mdi:lock"),
    "panel_alignment": ("Panel alignment", "mdi:grid"),
}

FEATURE_PLATFORMS = ("select", "switch", "number", "sensor")
EXEC_FEATURES = {"picture_mode_reset", "pic_pos_save", "pic_pos_del"}

LENS_BUTTONS: dict[str, tuple[str, str]] = {
    "lens_focus_far": ("Focus far", "mdi:image-filter-center-focus-strong"),
    "lens_focus_near": ("Focus near", "mdi:image-filter-center-focus-strong-outline"),
    "lens_zoom_up": ("Zoom in", "mdi:magnify-plus"),
    "lens_zoom_down": ("Zoom out", "mdi:magnify-minus"),
    "lens_shift_up": ("Lens shift up", "mdi:arrow-up-bold"),
    "lens_shift_down": ("Lens shift down", "mdi:arrow-down-bold"),
    "lens_shift_left": ("Lens shift left", "mdi:arrow-left-bold"),
    "lens_shift_right": ("Lens shift right", "mdi:arrow-right-bold"),
}

# Friendly labels for choices the projector reports (raw values otherwise).
SELECT_STATES: dict[str, dict[str, str]] = {
    "picture_mode": {
        "cinema_film1": "Cinema Film 1",
        "cinema_film2": "Cinema Film 2",
        "reference": "Reference",
        "tv": "TV",
        "photo": "Photo",
        "game": "Game",
        "brt_cinema": "Bright Cinema",
        "brt_tv": "Bright TV",
        "imax_enhanced": "IMAX Enhanced",
        "user": "User",
        "user1": "User 1",
        "user2": "User 2",
        "user3": "User 3",
        "dynamic": "Dynamic",
        "standard": "Standard",
        "cinema": "Cinema",
        "presentation": "Presentation",
        "brt_priority": "Brightness priority",
        "multi_screen": "Multi-screen",
        "srgb": "sRGB",
        "vivid": "Vivid",
    },
    "aspect": {
        "normal": "Normal",
        "squeeze": "Squeeze",
        "stretch": "Stretch",
        "v_stretch": "V Stretch",
        "zoom": "Zoom",
        "zoom_1_85": "1.85:1 Zoom",
        "zoom_2_35": "2.35:1 Zoom",
        "full": "Full",
        "full1": "Full 1",
        "full2": "Full 2",
        "full3": "Full 3",
        "4_3": "4:3",
        "16_9": "16:9",
    },
    "motionflow": {
        "off": "Off",
        "smooth_high": "Smooth High",
        "smooth_low": "Smooth Low",
        "impulse": "Impulse",
        "combination": "Combination",
        "true_cinema": "True Cinema",
    },
    "color_temp": {
        "d93": "D93",
        "d75": "D75",
        "d65": "D65",
        "d55": "D55",
        "high": "High",
        "mid": "Middle",
        "low": "Low",
        **{f"custom{i}": f"Custom {i}" for i in range(1, 6)},
    },
    "hdr": {
        "off": "Off",
        "auto": "Auto",
        "hdr10": "HDR10",
        "hlg": "HLG",
        "hdr_ref": "HDR Reference",
    },
    "pic_pos_sel": {f"custom{i}": f"Position {i}" for i in range(1, 7)},
    "color_space": {
        "bt709": "BT.709",
        "bt2020": "BT.2020",
        "dci": "DCI",
        **{f"custom{i}": f"Custom {i}" for i in range(1, 5)},
        **{f"color_space{i}": f"Color space {i}" for i in range(1, 4)},
    },
    "nr": {"off": "Off", "auto": "Auto", "low": "Low", "middle": "Middle", "high": "High"},
    "contrast_enh": {"off": "Off", "low": "Low", "mid": "Middle", "high": "High"},
    "light_output_mode": {
        "high": "High",
        "mid": "Middle",
        "low": "Low",
        "custom": "Custom",
        "auto": "Auto",
        "extended": "Extended",
    },
    "dyn_light_ctrl": {"off": "Off", "limited": "Limited", "full": "Full"},
    "dynamic_range": {"auto": "Auto", "limited": "Limited", "full": "Full"},
    "2d3d_sel": {"auto": "Auto", "2d": "2D", "3d": "3D"},
    "image_flip": {
        "off": "Off",
        "h": "Horizontal",
        "v": "Vertical",
        "hv": "Horizontal and vertical",
    },
    "film_mode": {"auto": "Auto", "off": "Off"},
}

POWER_STATES = {
    "standby": "Standby",
    "startup": "Starting up",
    "on": "On",
    "cooling1": "Cooling down",
    "cooling2": "Cooling down (stage 2)",
    "saving_cooling1": "Power saving cooling",
    "saving_cooling2": "Power saving cooling (stage 2)",
    "saving_standby": "Power saving standby",
    "update": "Updating firmware",
}

BASE: dict = {
    "config": {
        "flow_title": "{model} ({host})",
        "step": {
            "pick": {
                "title": "Select a projector",
                "description": "These Sony projectors announced themselves on your network.",
                "data": {"device": "Projector"},
            },
            "manual": {
                "title": "Connect to a Sony projector",
                "description": (
                    "Enable **ADCP** on the projector (web page → Setup → ADCP). For "
                    "discovery and instant power updates also enable **Advertisement**, "
                    "and keep the projector reachable in standby (Standby mode: Standard)."
                ),
                "data": {"host": "Host", "port": "Port"},
                "data_description": {
                    "host": "IP address or hostname of the projector.",
                    "port": "ADCP port configured on the projector (default 53595).",
                },
            },
            "password": {
                "title": "Projector password",
                "description": "{host} requires authentication. Use the projector's web administrator password (factory default: Projector).",
                "data": {"password": "Password"},
                "data_description": {
                    "password": "The administrator password of the projector's web page."
                },
            },
            "discovery_confirm": {
                "title": "Sony projector discovered",
                "description": "Do you want to add the {model} at {host}?",
            },
            "reauth_confirm": {
                "title": "Re-authenticate {name}",
                "description": "The projector rejected the stored password. Enter the current web administrator password.",
                "data": {"password": "Password"},
                "data_description": {
                    "password": "The administrator password of the projector's web page."
                },
            },
            "reconfigure": {
                "title": "Reconfigure projector",
                "data": {"host": "Host", "port": "Port", "password": "Password"},
                "data_description": {
                    "host": "IP address or hostname of the projector.",
                    "port": "ADCP port configured on the projector (default 53595).",
                    "password": "Leave empty when authentication is disabled on the projector.",
                },
            },
        },
        "error": {
            "cannot_connect": "Failed to connect. Check that ADCP is enabled and the address and port are correct.",
            "invalid_auth": "The projector rejected the password.",
            "password_required": "The projector requires a password.",
        },
        "abort": {
            "already_configured": "This projector is already configured.",
            "already_in_progress": "Configuration of this projector is already in progress.",
            "no_serial": "The projector did not report a serial number or MAC address.",
            "wrong_device": "This address belongs to a different projector.",
            "reauth_successful": "Re-authentication was successful.",
            "reconfigure_successful": "Reconfiguration was successful.",
        },
    },
    "options": {
        "step": {
            "init": {
                "title": "Projector options",
                "data": {
                    "scan_interval": "Polling interval while on",
                    "extra_commands": "Additional ADCP commands",
                },
                "data_description": {
                    "scan_interval": "How often settings are read while the projector is on. Standby and warm-up use their own fixed intervals.",
                    "extra_commands": "Extra command names to probe, such as `my_setting` or `my_setting --hdmi1`. Each supported one becomes a select, switch, number, button or sensor automatically.",
                },
            }
        },
        "error": {
            "invalid_command": "Use only lowercase command names, optionally followed by one --option."
        },
    },
    "selector": {"device": {"options": {"manual": "Enter address manually"}}},
    "exceptions": {
        "auth_failed": {"message": "The projector rejected the password."},
        "cannot_connect": {"message": "Cannot connect to the projector at {host}: {error}"},
        "communication_error": {"message": "Error communicating with the projector: {error}"},
        "invalid_value": {"message": "The projector rejected the value for `{command}`."},
        "command_inactive": {
            "message": "`{command}` is not available right now (check power, input and signal)."
        },
        "command_unsupported": {"message": "This projector does not support `{command}`."},
        "command_failed": {"message": "The projector answered `{code}` to `{command}`."},
        "outcome_unknown": {
            "message": "The connection dropped after the command was sent. It may or may not have been executed."
        },
        "entry_not_found": {"message": "No Sony projector with entry ID {entry_id}."},
        "entry_not_loaded": {"message": "{title} is not loaded."},
        "invalid_command": {"message": "Commands must be a single line of printable ASCII."},
        "probe_requires_power": {
            "message": "Turn the projector on before probing its capabilities."
        },
    },
    "services": {
        "send_command": {
            "name": "Send ADCP command",
            "description": "Sends a raw ADCP command line and returns the projector's reply.",
            "fields": {
                "config_entry_id": {
                    "name": "Projector",
                    "description": "The projector to send to.",
                },
                "command": {
                    "name": "Command",
                    "description": 'Raw ADCP command, for example `aspect ?`, `motionflow --info` or `pic_pos_sel "custom2"`.',
                },
            },
        },
        "probe_capabilities": {
            "name": "Probe capabilities",
            "description": "Re-asks the projector which commands it supports, adds entities for new ones and returns the full list.",
            "fields": {
                "config_entry_id": {
                    "name": "Projector",
                    "description": "The projector to probe. It must be on.",
                },
            },
        },
    },
}


def build() -> tuple[dict, dict]:
    entity: dict[str, dict] = {
        "binary_sensor": {
            "error": {"name": "Error"},
            "warning": {"name": "Warning"},
        },
        "button": {},
        "number": {},
        "remote": {"remote": {"name": "Remote"}},
        "select": {},
        "sensor": {
            "power_status": {"name": "Power status", "state": POWER_STATES},
            "signal": {"name": "Input signal"},
            "operation_hours": {"name": "Operation time"},
            "light_source_hours": {"name": "Light source time"},
        },
        "switch": {},
    }
    icons: dict[str, dict] = {
        "binary_sensor": {
            "error": {"default": "mdi:alert-circle-check", "state": {"on": "mdi:alert-circle"}},
            "warning": {"default": "mdi:alert-check", "state": {"on": "mdi:alert"}},
        },
        "button": {},
        "number": {},
        "remote": {"remote": {"default": "mdi:remote"}},
        "select": {},
        "sensor": {
            "power_status": {"default": "mdi:power"},
            "signal": {"default": "mdi:video-input-hdmi"},
            "operation_hours": {"default": "mdi:timer-outline"},
            "light_source_hours": {"default": "mdi:lightbulb-on-outline"},
        },
        "switch": {},
    }
    for key, (name, icon) in FEATURE_NAMES.items():
        if key in EXEC_FEATURES:
            platforms: tuple[str, ...] = ("button",)
        else:
            platforms = FEATURE_PLATFORMS
        for platform in platforms:
            item: dict = {"name": name}
            if platform == "select" and key in SELECT_STATES:
                item["state"] = SELECT_STATES[key]
            entity[platform][key] = item
            icons[platform][key] = {"default": icon}
    for key, (name, icon) in LENS_BUTTONS.items():
        entity["button"][key] = {"name": name}
        icons["button"][key] = {"default": icon}

    strings = {**BASE, "entity": {k: dict(sorted(v.items())) for k, v in sorted(entity.items())}}
    icon_file = {
        "entity": {k: dict(sorted(v.items())) for k, v in sorted(icons.items())},
        "services": {
            "send_command": {"service": "mdi:console-line"},
            "probe_capabilities": {"service": "mdi:radar"},
        },
    }
    return strings, icon_file


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    strings, icons = build()
    targets = {
        COMPONENT / "translations" / "en.json": _dump(strings),
        COMPONENT / "icons.json": _dump(icons),
    }
    if "--check" in sys.argv:
        stale = [str(p) for p, text in targets.items() if not p.exists() or p.read_text() != text]
        if stale:
            print("Out of date, run script/generate_translations.py:", *stale, sep="\n  ")
            return 1
        return 0
    for path, text in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
