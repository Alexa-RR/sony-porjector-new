<img src="custom_components/sony_adcp_projector/brand/icon.png" width="96" height="96" alt="">

# Sony Projector (ADCP) for Home Assistant

A local, push-capable Home Assistant integration for Sony projectors that speak
**ADCP** (Advanced Display Control Protocol). It was written for the
**VPL-GTZ380** and also targets other ADCP models, such as the VPL-XW, VPL-VW and
business VPL-F series.

It replaces the built-in `sony_projector` integration, which uses the old SDCP
(PJ Talk) protocol and only offers an on/off switch.

## How it works

Sony doesn't publish a command list per model, and command names differ between
product lines. So the integration asks the projector itself:

1. When the projector is on, every candidate command in
   [`catalog.py`](custom_components/sony_adcp_projector/catalog.py) is sent with
   `--info`.
2. Each command the projector supports becomes an entity of the right kind:
   - a choice becomes a **select**, or a **switch** when the only choices are on/off
   - a value becomes a **number**, with the projector's own min, max and step
   - an action becomes a **button**, one per choice where there are choices
   - a status becomes a **sensor**
3. The result is stored, so entities stay registered while the projector is in
   standby. Commands the projector doesn't support never create entities.

New entities appear on their own the first time the projector is switched on,
with no restart needed.

## Features

| Area | Entities |
| --- | --- |
| Power and input | Media player (on/off, source list read from the projector, including HDMI and DisplayPort), power status sensor (standby, startup, on, cooling…) |
| Picture (Calib. Preset) | Picture mode, Reality Creation and its resolution and noise filtering, laser light output and mode, dynamic control, Dynamic HDR Enhancer, contrast enhancer / D.Contrast Optimizer, Motionflow, contrast, brightness, color, hue, color temperature, sharpness, noise reduction, smooth gradation, gamma, HDR, color space, input lag reduction, custom color-temperature gain/bias, color correction |
| Screen | Aspect, **Picture Position** (lens memory) recall plus save and delete buttons per slot, blanking |
| Lens | Focus near/far, zoom in/out, and shift up/down/left/right buttons |
| Function | 2D/3D, 3D format, dynamic range, HDMI signal format, test pattern, settings lock |
| Setup and installation | High altitude, remote start, standby mode, power saving, menu language and position, image flip, anamorphic lens, trigger, IR receiver, lens and key locks |
| Status | Input signal, error and warning binary sensors (codes as attributes), operation and light-source hours |
| Remote | `remote.send_command` with any Sony key code, for example `menu`, `up`, `enter`, `return` or `lens_focus_far` |

Not every row exists on every model. You only get what your projector reports.

Rarely used configuration entities are **disabled by default**. Enable them from
the device page.

## Tested hardware

**VPL-GTZ380** (firmware as of November 2026, authentication off). Real probe
result: 48 supported commands, including

- **Inputs:** `hdmi1`, `hdmi2`, `dp1`, `dp2` and `dp1_2` (DisplayPort 1+2)
- **Picture:** picture mode (incl. Cinema Digital), Reality Creation and its
  sliders, laser light output (0-1000), dynamic laser control (off/limited/full),
  contrast enhancer, Motionflow (incl. Impulse 1-3), contrast, brightness, color,
  hue, sharpness, NR, color temperature (D93…D55, DCI, Custom 1-5) with gain/bias,
  gamma (1.8-2.6, Gamma 7-10), HDR (auto, HDR10, HLG, HDR Reference), color
  space, color correction, input lag reduction
- **Screen and lens:** aspect (incl. 1.85:1 / 2.35:1 zoom), Picture Position
  recall (1.85:1, 2.35:1, Custom 1-3), anamorphic lens (1.24x/1.32x)
- **Function and setup:** 2D/3D, 3D format, test pattern, settings lock,
  infrared, high altitude, remote start, power saving, menu language and
  position, status display, image flip, IR receiver, lens lock, panel alignment

Over ADCP the GTZ380 doesn't answer Dynamic HDR Enhancer, Smooth Gradation,
Picture Position save/delete, Blanking or dynamic range under any name tried.
Use the projector menu or the IR remote for those. The GTZ380 answers metadata
queries only in the `command ? --info` form, which the integration handles.
Picture settings read as *unavailable* while there's no input signal, because
the projector greys out its picture menu.

## Projector preparation

On the projector's web page (Setup):

1. **ADCP**: turn on *Start ADCP Service*. Authentication can stay on; the
   password is the web administrator password (factory default `Projector`).
2. **Advertisement**: turn it on to enable auto-discovery, instant power-state
   updates and automatic handling of IP address changes.
3. Keep the network active in standby (*Standby mode: Standard* or *Network
   management: On*). Otherwise the projector can't be turned on remotely.
4. If you use ADCP's *Host address list*, add Home Assistant's IP address.

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories* → add this repository as an **Integration**.
2. Install **Sony Projector (ADCP)** and restart Home Assistant.

### Manual

Copy `custom_components/sony_adcp_projector` into your `config/custom_components`
folder and restart.

Requires Home Assistant **2026.10** or newer.

## Configuration

*Settings → Devices & services → Add integration → Sony Projector (ADCP)*.

Projectors that advertise themselves are listed automatically. You can also enter
the host and port (default `53595`). You're only asked for a password if the
projector requires one.

| Option | Description |
| --- | --- |
| Polling interval while on | How often settings are read while the projector is on (default 15 s). Standby is checked every 30 s and warm-up/cool-down every 2 s. |
| Additional ADCP commands | Extra command names to probe, such as `my_setting` or `my_setting --hdmi1`. Each supported one becomes an entity automatically. |

Address, port and password can be changed later with **Reconfigure**. A rejected
password starts a re-authentication prompt.

## Actions

### `sony_adcp_projector.send_command` (admin only)

Sends any raw ADCP line and returns the reply:

```yaml
action: sony_adcp_projector.send_command
data:
  config_entry_id: YOUR_ENTRY_ID
  command: 'pic_pos_sel "custom2"'
response_variable: reply
```

Use `<command> ?` to read a value, `<command> --info` to see its type and range,
and `<command> --range` to list its choices.

### `sony_adcp_projector.probe_capabilities`

Re-asks the projector, which must be on, for everything it supports. It adds
entities for anything new and returns the full supported and unsupported list.
Run it after a firmware update, or attach the output to a feature request.

## Automation examples

Switch the lens memory and aspect for scope films:

```yaml
- action: select.select_option
  target: { entity_id: select.vpl_gtz380_picture_position }
  data: { option: custom2 }
- action: select.select_option
  target: { entity_id: select.vpl_gtz380_aspect }
  data: { option: squeeze }
```

Open the projector menu from a dashboard button:

```yaml
action: remote.send_command
target: { entity_id: remote.vpl_gtz380_remote }
data: { command: menu }
```

## Data updates

- **Power**: an SDAP advertisement triggers an immediate refresh. Status is also
  polled every 30 s in standby and every 2 s while warming up or cooling down.
- **Settings**: read every *Polling interval* while the projector is fully on,
  and right after each change you make (picture-mode changes affect other values).
- **Hour counters**: read every 10 minutes.

## Known limitations

- Most settings can only be read while the projector is **on**. In standby they
  show as unavailable, which is by design.
- Some settings are only available for certain signals. For example, HDR settings
  need an HDR source, and those settings show as unavailable otherwise.
- Lens buttons send single remote-key steps. The projector doesn't report the
  absolute lens position.
- Sony's published command lists cover business models. GTZ/XW/VW command names
  are inferred and verified at runtime. Use *probe_capabilities* and diagnostics
  to see exactly what your unit supports.

## Troubleshooting

- **Cannot connect**: check that ADCP is on, the port matches, and the HA host is
  in the ADCP host address list (if one is set).
- **Not discovered**: turn on Advertisement, and make sure UDP 53862 broadcasts
  can reach HA (same subnet or VLAN, firewall).
- **An expected setting is missing**: power the projector on, run
  *probe_capabilities*, then download diagnostics. The `capabilities` section
  lists every command and how the projector answered.
- Debug logging:

  ```yaml
  logger:
    logs:
      custom_components.sony_adcp_projector: debug
  ```

## Removal

*Settings → Devices & services → Sony Projector (ADCP) → ⋮ → Delete*, then
remove the folder (or uninstall it in HACS). Stored capability data is deleted
together with the entry.

## Development

```bash
uv venv -p 3.14 .venv && uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
python script/generate_translations.py   # after editing names or catalog entries
```

The tests run against a fake projector that speaks real ADCP over TCP
([`tests/fake_projector.py`](tests/fake_projector.py)). The protocol code in
[`adcp/`](custom_components/sony_adcp_projector/adcp) has no Home Assistant
imports, so it can be published to PyPI as its own library.

## License

[MIT](LICENSE)
