"""Consume exported native image output, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/inkscape-purifier"
original = Path(sys.argv[2]).resolve()
source = Path(__file__).resolve().parents[1]
resources = Path(sys.argv[3]).resolve()


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=False, env=env, cwd=cwd, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="inkscape-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".inkscape-purifier"),
    )
    env = os.environ.copy() | {
        "HOME": str(root / "home"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    for name in ["home", "data", "config", "cache"]:
        (root / name).mkdir()
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
    ]:
        env.pop(key, None)
    env.update(
        FONTCONFIG_FILE=str(resources / "fonts.conf"),
        NO_AT_BRIDGE="1",
        GTK_USE_PORTAL="0",
        GSETTINGS_BACKEND="memory",
        DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(root / "no-system-bus"),
    )
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    image = build / "drawing.svg"
    width = call(
        [
            str(original / "bin/inkscape"),
            str(image),
            "--query-id=b-drawing",
            "--query-width",
        ],
        env=env,
        cwd=root,
    )
    assert float(width) == 40, width
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "inkscape-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert (
            tar.extractfile("./drawing.svg").read()
            == (build / "drawing.svg").read_bytes()
        )
    external = root / "external-lock.json"
    shutil.copyfile(project / "inkscape-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "INKSCAPE_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("native Inkscape artifact consumers passed")
