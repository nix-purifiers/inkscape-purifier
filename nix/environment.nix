{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  pythonSdk,
  nativeVersion,
  original,
  purifier,
  sdk,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  archives = purifier.tree (
    {
      name = "inkscape-extension-archives";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  request = writeText "inkscape-native-install.json" (
    builtins.toJSON {
      action = "install";
      entries = checked.entries;
      inherit (checked.data.native) metadata modules;
      archives = builtins.listToAttrs (
        map (entry: {
          name = entry.path;
          value = "${archives}/${entry.path}";
        }) checked.entries
      );
    }
  );
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = ../native/inkscape_purifier_helper.py;
  };
  manifest = writeText "inkscape-lock.json" (builtins.toJSON checked.data);
in
assert lib.assertMsg (
  checked.data.sdk == sdk
) "Inkscape SDK changed; run inkscape-purifier lock --update";
runCommand "inkscape-locked-extensions" { } ''
  export HOME="$TMPDIR/home" XDG_CONFIG_HOME="$TMPDIR/config" XDG_DATA_HOME="$TMPDIR/data" XDG_CACHE_HOME="$TMPDIR/cache"
  mkdir -p "$HOME" "$out/extensions"
  export INKSCAPE_PROFILE_DIR="$out/extensions" INKSCAPE_VERSION=${nativeVersion}
  export INKSCAPE_PURIFIER_ORIGINAL=${original} PYTHONNOUSERSITE=1 PYTHONPYCACHEPREFIX="$TMPDIR/python-cache"
  ${pythonSdk}/bin/python3 ${driver}/inkscape_purifier_helper.py ${request} "$TMPDIR/response.json"
  ${pythonSdk}/bin/python3 -m venv --without-pip --system-site-packages "$out/venv"
  ln -s ${manifest} "$out/lock.json"
''
