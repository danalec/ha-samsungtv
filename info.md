# Home Assistant - SamsungTV Custom

Control Samsung TVs from Home Assistant, including 2021 and newer models.

This is the official `samsungtv` integration from `home-assistant/core`, adapted to the `samsungtv_custom` domain and
extended with **key chaining** — send a sequence of keys with explicit delays, so the TV follows a menu instead of
dropping keys sent too fast.

**Rebuilt on the current protocol layer.** The previous base only spoke the legacy port and the plain websocket, so the
H and J series — a large slice of the 2021-onward range — had no working transport and failed silently. This one speaks
all three, including the encrypted websocket on port 8000 with PIN pairing.

**Two entities per TV:** a `media_player` (power, volume, mute, transport, sources) and a `remote` (raw key commands with
repeat). Setup happens entirely in the UI, over DHCP, SSDP or zeroconf discovery.

**Requires Home Assistant 2026.10.0+ and Python 3.14.2+.** TV models from 2016 onwards.

Turning the TV on sends a **wake-on-LAN** packet when a usable MAC is known — Neo QLEDs wake from deep standby, despite
being commonly documented as ignoring those. If you attach a **turn on automation** to the TV as a device trigger, that
automation runs too, which is how an HDMI-CEC capable device or another hub joins in.

Please refer to the [readme](https://github.com/danalec/ha-samsungtv#readme) for setup, key chaining patterns and the full
list of features.

Credits
-------

Maintained by [danalec](https://github.com/danalec).

The protocol layer, config flow and entity model are taken from the official Home Assistant `samsungtv` integration, which
descends from [ha-samsungtv-custom](https://github.com/roberodin/ha-samsungtv-custom) by
[roberodin](https://github.com/roberodin) → [SamsungTV Tizen](https://github.com/jaruba/ha-samsungtv-tizen) by
[jaruba](https://github.com/jaruba) → [SamsungTV Smart](https://github.com/ollo69/ha-samsungtv-smart) by
[ollo69](https://github.com/ollo69).

Logo support in that lineage was based on [jaruba channel-logos](https://github.com/jaruba/channel-logos), developed with
the support of [Screwdgeh](https://github.com/Screwdgeh). Logos are not part of this component.
