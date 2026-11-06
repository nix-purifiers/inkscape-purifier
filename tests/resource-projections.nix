# SPDX-License-Identifier: MIT
{ pkgs, build }:
let
  plain = build { src = ../examples/minimal; };
  args = {
    src = ../examples/minimal;
    resourceRoots."drawing.svg" = "drawing.svg";
    doCheck = true;
    checkCommand = ''
      test -s "$out/drawing.svg"
      printf 'private sibling\n' > "$out/private.txt"
    '';
  };
  selected = build args;
  rejects =
    name: roots: expected:
    let
      actual = (build (args // { resourceRoots = roots; })).projections.resources;
    in
    actual.overrideAttrs (old: {
      name = "inkscape-resource-reject-${name}";
      buildCommand = ''
        if ( ${old.buildCommand} ) > "$TMPDIR/rejection.log" 2>&1; then
          echo "unexpectedly accepted ${name}" >&2
          exit 1
        fi
        ${pkgs.lib.concatMapStringsSep "\n" (
          message: "grep -F -- ${pkgs.lib.escapeShellArg message} \"$TMPDIR/rejection.log\""
        ) expected}
        mkdir -p "$out"
        cp "$TMPDIR/rejection.log" "$out/rejection.log"
      '';
    });
  missing = rejects "missing-output" { "missing.svg" = "missing.svg"; } [
    "FileNotFoundError:"
    "missing.svg"
  ];
  unsafeSource = rejects "source-traversal" { "drawing.svg" = "../private.txt"; } [
    "canonical relative resource path: ../private.txt"
  ];
  unsafeDestination = rejects "destination-traversal" { "../escape.svg" = "drawing.svg"; } [
    "canonical relative resource path: ../escape.svg"
  ];
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
  test -e ${missing}
  test -e ${unsafeSource}
  test -e ${unsafeDestination}
  test -e ${selected.packages.project}/private.txt
  python - <<'PY'
  import hashlib, json, pathlib, zipfile, xml.etree.ElementTree as ET
  root = pathlib.Path('${projection.directory}')
  catalog = json.load(open('${projection.catalog}'))
  assert sorted(catalog['files']) == ['drawing.svg']
  exported = (root / 'drawing.svg').read_bytes()
  native = pathlib.Path('${selected.packages.project}/drawing.svg').read_bytes()
  assert hashlib.sha256(exported).digest() == hashlib.sha256(native).digest()
  with zipfile.ZipFile('${projection.classPath}') as jar:
      assert jar.namelist() == ['drawing.svg']
      assert jar.read('drawing.svg') == native
  svg = ET.fromstring(exported)
  assert svg.tag == '{http://www.w3.org/2000/svg}svg'
  PY
  touch $out
''
