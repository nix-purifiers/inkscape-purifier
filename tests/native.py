"""Native extension actions, preferences, code boundaries, venv, HTTP and fallback."""

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

cli = Path(sys.argv[1]).resolve()
original = Path(sys.argv[2]).resolve()
source = Path(__file__).resolve().parents[1]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"project networking works")

    def log_message(self, *args):
        pass


def group(parent, id):
    result = parent.find("./group[@id='" + id + "']")
    return result if result is not None else ET.SubElement(parent, "group", id=id)


with tempfile.TemporaryDirectory(prefix="inkscape-native-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".inkscape-purifier", "output"),
    )
    env = os.environ.copy()
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
    ]:
        (root / name).mkdir()
        env[key] = str(root / name)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    marker = root / "ambient-ran"
    poison_marker = root / "interpreter-ran"
    ambient = root / "shared/extensions"
    ambient.mkdir(parents=True)
    (ambient / "ambient.inx").write_text(
        """<inkscape-extension xmlns="http://www.inkscape.org/namespace/inkscape/extension"><name>Ambient</name><id>org.purifier.ambient</id><effect><object-type>all</object-type></effect><script><command interpreter="python" location="inx">ambient.py</command></script></inkscape-extension>"""
    )
    (ambient / "ambient.py").write_text(
        "import inkex\nfrom pathlib import Path\nclass Ambient(inkex.EffectExtension):\n def effect(self):Path("
        + repr(str(marker))
        + ").write_text('ran')\nAmbient().run()\n"
    )
    poison = root / "python-poison"
    poison.write_text("#!/bin/sh\ntouch " + str(poison_marker) + "\nexit 1\n")
    poison.chmod(0o755)
    script = project / "build.py"
    script.write_text(
        script.read_text()
        + f"""
import sys,stat,urllib.request,json
from inkman.target import ExtensionsTarget
from inkman.backfoot import update_pip_package
assert Path(sys.prefix)==Path(os.environ['VIRTUAL_ENV'])
assert Path(sys.prefix).is_relative_to('/nix/store')
assert not (Path(sys.prefix).stat().st_mode & stat.S_IWUSR)
assert Path(sys.pycache_prefix).is_relative_to('/nix/store')
target=ExtensionsTarget('extension','Extensions','extensions',True,filters=('*.inx',))
assert Path(target.path)==Path(os.environ['INKSCAPE_PURIFIER_EXTENSIONS'])
assert not target.is_writable()
assert [item.ident for item in target.list_installed(cached=False)]==['org.inkscape.extension.6851']
for method,arguments in [(target._install,('/not-a-zip',{{}})),(target.write_file,(b'bad','bad.py')),(target.pip_install,('/not-a-wheel',)),(target.pip_uninstall,('bad',)),(update_pip_package,('bad',))]:
 try:method(*arguments)
 except RuntimeError as error:assert 'locked' in str(error)
 else:raise AssertionError('native installer was not frozen')
with urllib.request.urlopen('http://127.0.0.1:{server.server_port}/') as response:assert response.read()==b'project networking works'
assert not Path({str(marker)!r}).exists(),'locked shared extension executed'
assert not Path({str(poison_marker)!r}).exists(),'locked interpreter preference executed'
settings=Path('control.json')
if settings.exists():
 mode=json.loads(settings.read_text())['mode']
 native_env=os.environ.copy()
 native_env['INKSCAPE_DATADIR']={str(original / "share")!r}
 for key in ['INKSCAPE_PURIFIER_EXTENSIONS','INKSCAPE_PURIFIER_PYTHON']:native_env.pop(key,None)
 action='org.purifier.ambient.noprefs' if mode=='shared' else 'de.vektorrascheln.realscale.noprefs'
 result=subprocess.run([{str(original / "bin/inkscape")!r},'--with-gui','--batch-process',str(source),'--actions=select-by-id:a-reference,b-drawing;'+action],env=native_env,capture_output=True,text=True,check=False)
 marker=Path({str(marker)!r}) if mode=='shared' else Path({str(poison_marker)!r})
 assert marker.exists(),result.stdout+result.stderr
 marker.unlink()
"""
    )
    args = [cli / "bin/inkscape-purifier", "--project", project]
    before = (project / "inkscape-purifier.lock.json").read_bytes()
    hashes = []
    try:
        for counter, width in enumerate([4, 5, 4], 1):
            (project / "source.svg").write_text(
                (source / "examples/minimal/source.svg")
                .read_text()
                .replace('width="4"', f'width="{width}"')
            )
            if counter > 1:
                preferences = project / ".inkscape-purifier/run/profile/preferences.xml"
                tree = ET.parse(preferences)
                group(group(tree.getroot(), "options"), "resources").set(
                    "sharedpath", str(ambient.parent)
                )
                if counter == 3:
                    group(tree.getroot(), "extensions").set(
                        "python-interpreter", str(poison)
                    )
                group(tree.getroot(), "purifier").set("counter", str(counter))
                tree.write(preferences, encoding="UTF-8", xml_declaration=True)
                (project / "control.json").write_text(
                    json.dumps({"mode": "shared" if counter == 2 else "python"})
                )
            result = subprocess.run(
                [*args, "run", "build.py"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            if counter > 1:
                tree = ET.parse(
                    project / ".inkscape-purifier/run/profile/preferences.xml"
                )
                assert group(tree.getroot(), "purifier").get("counter") == str(counter)
            output = project / "output/drawing.svg"
            tree = ET.parse(output)
            rect = tree.find(".//*[@id='b-drawing']")
            assert (
                float(rect.get("width")) == width
                and rect.get("transform") == "scale(10, 10)"
            )
            hashes.append(hashlib.sha256(output.read_bytes()).hexdigest())
            assert (project / "inkscape-purifier.lock.json").read_bytes() == before
    finally:
        server.shutdown()
        server.server_close()
    assert hashes[0] != hashes[1] and hashes[0] == hashes[2]
    (project / "failure.py").write_text("raise SystemExit(7)\n")
    result = subprocess.run(
        [*args, "run", "failure.py"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7, result.stdout + result.stderr
    (project / "inkscape-purifier.json").write_text('{"extensions": []}')
    wrapper_env = env | {"INKSCAPE_PURIFIER_PROJECT": str(project)}
    result = subprocess.run(
        [cli / "bin/inkscape", "--version"],
        env=wrapper_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode and "selection changed" in result.stderr
    (project / "inkscape-purifier.lock.json").unlink()
    for arguments in [["--version"], ["--purifier-invalid"]]:
        expected = subprocess.run(
            [original / "bin/inkscape", *arguments],
            env=env,
            capture_output=True,
            check=False,
        )
        actual = subprocess.run(
            [cli / "bin/inkscape", *arguments],
            env=wrapper_env,
            capture_output=True,
            check=False,
        )
        assert actual.returncode == expected.returncode
        assert actual.stdout == expected.stdout
        assert (
            actual.stderr
            == b"warning: no Inkscape purifier lock; using ordinary, impure extension resolution\n"
            + expected.stderr
        )
print(
    "Inkscape native edits/preferences/shared paths/interpreter/venv/HTTP/fallback passed"
)
