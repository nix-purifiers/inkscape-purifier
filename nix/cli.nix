{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  python3,
  original,
  lockedSdk,
  pythonSdk,
  nativeVersion,
  xvfb-run,
  dbus,
  sdk,
  emptyCache,
  fontConfig,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.hasExt "py") ../inkscape_purifier)
      (lib.fileset.fileFilter (file: file.hasExt "py") ../native)
      (lib.fileset.fileFilter (file: file.hasExt "nix") ./.)
    ];
  };
  bootstrap = writeText "inkscape-purifier-main.py" "import os,runpy,sys; sys.path.insert(0, ${builtins.toJSON integration}); sys.argv[0]=os.environ['INKSCAPE_PURIFIER_COMMAND']; runpy.run_module('inkscape_purifier.main',run_name='__main__')";
  realize = writeText "inkscape-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = if target == "environment" then builtins.toPath projectPath else builtins.path {
        path = builtins.toPath projectPath;
        name = "inkscape-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".inkscape-purifier" "__pycache__" "result" "output" ]);
      };
      build = scope.buildInkscapeProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown INKSCAPE purifier target"
  '';
in
runCommand "inkscape-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in inkscape-purifier inkscape; do
    makeWrapper ${python3}/bin/python "$out/bin/$name" \
      --add-flags ${bootstrap} \
      --set INKSCAPE_PURIFIER_COMMAND "$name" \
      --set INKSCAPE_PURIFIER_NATIVE ${integration}/native \
      --set INKSCAPE_PURIFIER_ORIGINAL ${original} \
      --set INKSCAPE_PURIFIER_LOCKED_SDK ${lockedSdk} \
      --set INKSCAPE_PURIFIER_PYTHON_SDK ${pythonSdk} \
      --set INKSCAPE_PURIFIER_NATIVE_VERSION ${nativeVersion} \
      --set INKSCAPE_PURIFIER_XVFB ${xvfb-run} \
      --set INKSCAPE_PURIFIER_DBUS ${lib.getBin dbus} \
      --set INKSCAPE_PURIFIER_SDK ${sdk} \
      --set INKSCAPE_PURIFIER_CACHE ${emptyCache} \
      --set INKSCAPE_PURIFIER_FONTS ${fontConfig} \
      --set INKSCAPE_PURIFIER_REALIZE ${realize} \
      --set-default INKSCAPE_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
        ]
      }
  done
''
