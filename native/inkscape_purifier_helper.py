"""Use the SDK's native gallery client, package model and archive installer."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sdk = Path(os.environ["INKSCAPE_PURIFIER_ORIGINAL"])
sys.path.insert(0, str(sdk / "share/inkscape/extensions/inkman/inkman"))
from inkex.inx import InxFile
from inkman.archive import Archive
from inkman.package import PackageItem
from inkman.target import ExtensionsTarget


def safe_name(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("unsafe native archive path")
    return path


def inspect_archive(target, filename):
    if not str(filename).endswith(".zip") or target.is_pip_package(str(filename)):
        raise ValueError(
            "only native ZIP Python extensions are supported; pip packages need a provider"
        )
    modules = []
    with Archive(str(filename)) as archive:
        names = list(archive.filenames())
        for name in names:
            safe_name(name)
        for name in names:
            if not name.endswith(".inx"):
                continue
            # Parse native descriptors without importing their executable code.
            native = InxFile(archive.read(name))
            script = native.script
            if script.get("interpreter") != "python" or script.get("location") not in {
                None,
                "inx",
            }:
                raise ValueError("only native Python INX scripts are supported")
            script_path = PurePosixPath(name).parent / safe_name(script["script"])
            if str(script_path) not in names:
                raise ValueError("native INX script is missing from its archive")
            modules.append(
                {
                    "id": native.ident,
                    "name": native.name,
                    "descriptor": name,
                    "script": str(script_path),
                }
            )
    if not modules:
        raise ValueError("extension archive has no native INX descriptors")
    return modules


def checked_item(info):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", info["id"]):
        raise ValueError("unsupported native package ID")
    item = PackageItem(info)
    if not item.verified or os.environ["INKSCAPE_VERSION"] not in item.targets:
        raise ValueError("native package is not verified for this SDK")
    return item


def capture(request):
    target = ExtensionsTarget(
        "extension", "Extensions", "extensions", True, filters=("*.inx",)
    )
    entries = []
    metadata = {}
    modules = {}
    for selected in request["extensions"]:
        found = [
            item
            for item in target.search(selected["query"], filtered=True)
            if item.ident == selected["id"]
        ]
        if len(found) != 1:
            raise ValueError(
                "native gallery query did not resolve exactly one selected ID"
            )
        item = found[0]
        checked_item(item.info)
        if not item.is_installable(os.environ["INKSCAPE_VERSION"]):
            raise ValueError("native package is not installable")
        original = target._install

        def install(filename, info, item=item, original=original):
            modules[info["id"]] = inspect_archive(target, filename)
            entries.append(
                {
                    "path": info["id"] + ".zip",
                    "url": item.url,
                    "id": info["id"],
                    "bytesSha256": hashlib.sha256(
                        Path(filename).read_bytes()
                    ).hexdigest(),
                }
            )
            return original(filename, info)

        item.set_installer(install)
        item.install()
        metadata[item.ident] = item.info
    ids = sorted(item.ident for item in target.list_installed(cached=False))
    if ids != sorted(metadata):
        raise ValueError("native installed IDs differ from selection")
    return {"entries": entries, "metadata": metadata, "modules": modules}


def install(request):
    target = ExtensionsTarget("extension", "Extensions", "", True, filters=("*.inx",))
    for entry in request["entries"]:
        id = entry["id"]
        info = request["metadata"][id]
        checked_item(info)
        filename = request["archives"][entry["path"]]
        if entry["url"] != info["links"]["file"]:
            raise ValueError("native source URL differs from lock")
        if inspect_archive(target, filename) != request["modules"][id]:
            raise ValueError("native INX metadata differs from lock")
        expected = json.loads(json.dumps(info))
        target._install(filename, info)
        if info != expected:
            raise ValueError("native installed metadata differs from lock")
    ids = sorted(item.ident for item in target.list_installed(cached=False))
    if ids != sorted(request["metadata"]):
        raise ValueError("native installed IDs differ from lock")
    return {"installed": ids}


request = json.loads(Path(sys.argv[1]).read_text())
result = capture(request) if request["action"] == "capture" else install(request)
Path(sys.argv[2]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
