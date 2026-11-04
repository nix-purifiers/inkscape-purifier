{
  lib,
  runCommand,
  python3,
  lockedSdk,
  pythonSdk,
  xvfb-run,
  dbus,
  environment,
  readLock,
  emptyCache,
  fontConfig,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/inkscape-purifier.lock.json",
  script ? "build.py",
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
}:
let
  lock = readLock { inherit src lockFile; };
  profile = environment { inherit lock fetchers; };
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = lib.fileset.unions [
      ../native/inkscape_purifier_run_project.py
      ../native/inkscape_purifier_prepare.py
    ];
  };
  projectSource = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        ".inkscape-purifier"
        "__pycache__"
        "result"
        "output"
      ]);
  };
  project = runCommand "inkscape-project" { } ''
    export INKSCAPE_PURIFIER_ENVIRONMENT=${profile} INKSCAPE_PURIFIER_LOCKED_SDK=${lockedSdk} INKSCAPE_PURIFIER_PYTHON_SDK=${pythonSdk}
    export INKSCAPE_PURIFIER_CACHE=${emptyCache} INKSCAPE_PURIFIER_FONTS=${fontConfig}
    export INKSCAPE_PURIFIER_XVFB=${xvfb-run} INKSCAPE_PURIFIER_DBUS=${lib.getBin dbus}
    export INKSCAPE_PURIFIER_OUTPUT="$out" INKSCAPE_PURIFIER_STATE="$TMPDIR/inkscape-run"
    mkdir -p "$out"
    cp -r ${projectSource} project
    chmod -R u+w project
    cd project
    export INKSCAPE_PURIFIER_PROJECT="$PWD" INKSCAPE_PURIFIER_SCRIPT="$PWD/"${lib.escapeShellArg script}
    ${python3}/bin/python ${driver}/inkscape_purifier_run_project.py
    ${lib.optionalString doCheck checkCommand}
  '';
  release =
    runCommand "inkscape-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - -C ${project} . | gzip -n > "$out/inkscape-project.tar.gz"
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = profile;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
