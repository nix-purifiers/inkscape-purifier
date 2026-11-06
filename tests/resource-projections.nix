# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  plain = build { src = ../examples/minimal; };
  selected = build {
    src = ../examples/minimal;
    resourceRoots."drawing.svg" = "drawing.svg";
    doCheck = true;
    checkCommand = ''
      test -s "$out/drawing.svg"
      printf 'private sibling\n' > "$out/private.txt"
    '';
  };
  projection = selected.packages.project.projections.resources;
  consumers = import ./resource-consumer.nix {
    inherit pkgs projection;
    excluded = [
      "private.txt"
      "source.svg"
      "inkscape-purifier.lock.json"
    ];
  };
in
assert plain.projections == { };
assert selected.projections.resources == projection;
pkgs.runCommand "inkscape-resource-projections" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  test -e ${consumers}
  test -e ${selected.packages.project}/private.txt
  python - <<'PY'
  import hashlib, json, pathlib, xml.etree.ElementTree as ET
  root = pathlib.Path('${projection.directory}')
  catalog = json.load(open('${projection.catalog}'))
  assert sorted(catalog['files']) == ['drawing.svg']
  exported = (root / 'drawing.svg').read_bytes()
  native = pathlib.Path('${selected.packages.project}/drawing.svg').read_bytes()
  assert hashlib.sha256(exported).digest() == hashlib.sha256(native).digest()
  svg = ET.fromstring(exported)
  assert svg.tag == '{http://www.w3.org/2000/svg}svg'
  PY
  touch $out
''
