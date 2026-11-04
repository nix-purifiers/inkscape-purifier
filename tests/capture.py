"""Fresh native capture, cold replay and atomic failure against the public catalog."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/inkscape-purifier"
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="inkscape-capture-") as temporary:
    project = Path(temporary)
    shutil.copyfile(
        source / "examples/minimal/inkscape-purifier.json",
        project / "inkscape-purifier.json",
    )
    env = os.environ.copy() | {"INKSCAPE_PURIFIER_PROJECT": str(project)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=env, cwd=project)
    lock = project / "inkscape-purifier.lock.json"
    before = lock.read_bytes()
    subprocess.run([str(cli), "lock"], check=True, env=env, cwd=project)
    subprocess.run([str(cli), "prefetch"], check=True, env=env, cwd=project)
    assert lock.read_bytes() == before
    selection_file = project / "inkscape-purifier.json"
    selection = json.loads(selection_file.read_text())
    selection["extensions"].append(
        {
            "id": "org.inkscape.extension.999999999999",
            "query": "purifier_missing_probe_999999999999",
        }
    )
    selection_file.write_text(json.dumps(selection))
    failed = subprocess.run(
        [str(cli), "lock", "--update"], check=False, env=env, cwd=project
    )
    assert failed.returncode != 0 and lock.read_bytes() == before
    empty = project / "empty"
    empty.mkdir()
    (empty / "inkscape-purifier.json").write_text('{"extensions": []}\n')
    empty_env = env | {"INKSCAPE_PURIFIER_PROJECT": str(empty)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=empty_env, cwd=empty)
    subprocess.run(
        [str(cli), "exec", "--", "--version"], check=True, env=empty_env, cwd=empty
    )

print("native inkscape capture and atomic failure passed")
