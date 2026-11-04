"""Execute a project script through native Python, Inkscape and a private display."""

import os
import secrets
import signal
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from inkscape_purifier_prepare import prepare


def run_project(
    project,
    script,
    state,
    environment,
    sdk,
    python_sdk,
    cache,
    fonts,
    xvfb,
    dbus,
    output,
):
    state = Path(state).resolve()
    project = Path(project).resolve()
    env = os.environ.copy()
    for key in [
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "WAYLAND_SOCKET",
        "DBUS_SESSION_BUS_ADDRESS",
        "DBUS_STARTER_ADDRESS",
        "DBUS_STARTER_BUS_TYPE",
        "SESSION_MANAGER",
        "AT_SPI_BUS_ADDRESS",
        "GTK_MODULES",
        "GTK3_MODULES",
        "GTK_PATH",
        "QT_QPA_PLATFORMTHEME",
        "XDG_ACTIVATION_TOKEN",
        "DESKTOP_STARTUP_ID",
    ]:
        env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ]:
        path = state / name
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        env[key] = str(path)
    env = prepare(env, state, environment, sdk, python_sdk, cache)
    env.update(
        FONTCONFIG_FILE=str(fonts),
        GDK_BACKEND="x11",
        GTK_USE_PORTAL="0",
        NO_AT_BRIDGE="1",
        LIBGL_ALWAYS_SOFTWARE="1",
        GSETTINGS_BACKEND="memory",
        DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(state / "no-system-bus"),
        INKSCAPE_PURIFIER_OUTPUT=str(Path(output).resolve()),
    )
    bus = ET.Element("busconfig")
    ET.SubElement(bus, "type").text = "session"
    ET.SubElement(bus, "listen").text = "unix:abstract=inkscape-purifier-" + secrets.token_hex(12)
    ET.SubElement(bus, "auth").text = "EXTERNAL"
    policy = ET.SubElement(bus, "policy", context="default")
    for attr in ["own", "send_destination", "receive_sender"]:
        ET.SubElement(policy, "allow", {attr: "*"})
    bus_file = state / "bus.conf"
    ET.ElementTree(bus).write(bus_file, encoding="UTF-8", xml_declaration=True)
    args = [
        str(Path(xvfb) / "bin/xvfb-run"),
        "-a",
        str(Path(dbus) / "bin/dbus-run-session"),
        "--dbus-daemon=" + str(Path(dbus) / "bin/dbus-daemon"),
        "--config-file=" + str(bus_file),
        "--",
        str(Path(environment) / "venv/bin/python3"),
        str(Path(script).resolve()),
    ]
    process = subprocess.Popen(args, env=env, cwd=project, start_new_session=True)
    try:
        return process.wait()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    raise SystemExit(
        run_project(
            os.environ["INKSCAPE_PURIFIER_PROJECT"],
            os.environ["INKSCAPE_PURIFIER_SCRIPT"],
            os.environ["INKSCAPE_PURIFIER_STATE"],
            os.environ["INKSCAPE_PURIFIER_ENVIRONMENT"],
            os.environ["INKSCAPE_PURIFIER_LOCKED_SDK"],
            os.environ["INKSCAPE_PURIFIER_PYTHON_SDK"],
            os.environ["INKSCAPE_PURIFIER_CACHE"],
            os.environ["INKSCAPE_PURIFIER_FONTS"],
            os.environ["INKSCAPE_PURIFIER_XVFB"],
            os.environ["INKSCAPE_PURIFIER_DBUS"],
            os.environ["INKSCAPE_PURIFIER_OUTPUT"],
        )
    )
