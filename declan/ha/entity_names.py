"""Names Declan says out loud for Home Assistant entities."""


def spoken_label(friendly, device_name, id_name):
    """The light's own name, without its controller's name in front.

    ESPHome and similar boards name entities "<device> <light>" ("ESP32 BRMesh Mood Lights"),
    so Declan would read the chip name aloud. Drop a leading device name when something is left.
    """
    label = friendly.strip() if isinstance(friendly, str) and friendly.strip() else id_name
    if isinstance(device_name, str) and device_name.strip():
        prefix = " ".join(device_name.split())
        spaced = " ".join(label.split())
        if spaced.casefold().startswith(prefix.casefold() + " "):
            rest = spaced[len(prefix):].strip(" -:_")
            if rest:
                return rest
    return label
