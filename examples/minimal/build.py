"""Apply the installed extension through the native GTK action and export SVG."""

import os
import subprocess
from pathlib import Path

source = Path(__file__).resolve().parent / "source.svg"
output = Path(os.environ.get("INKSCAPE_PURIFIER_OUTPUT", "output"))
output.mkdir(exist_ok=True)
subprocess.run(
    [
        "inkscape",
        "--with-gui",
        "--batch-process",
        str(source),
        "--export-plain-svg",
        "--export-filename=" + str(output / "drawing.svg"),
        "--actions=select-by-id:a-reference,b-drawing;de.vektorrascheln.realscale.noprefs",
    ],
    check=True,
)
