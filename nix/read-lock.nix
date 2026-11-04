{ lib }:
{
  src,
  lockFile ? src + "/inkscape-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  selection =
    if builtins.pathExists (src + "/inkscape-purifier.json") then
      builtins.fromJSON (builtins.readFile (src + "/inkscape-purifier.json"))
    else
      null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "inkscape"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.selection or null)
    && data.selection == selection
    && builtins.isList (data.selection.extensions or null)
    && builtins.all (
      selected:
      builtins.isAttrs selected
      && builtins.isString (selected.id or null)
      && builtins.isString (selected.query or null)
    ) data.selection.extensions
    && builtins.isAttrs (data.native.metadata or null)
    && builtins.isAttrs (data.native.modules or null)
    && builtins.isList entries
    && builtins.all (
      entry:
      builtins.isAttrs entry
      && builtins.isString (entry.id or null)
      && builtins.match "[A-Za-z0-9][A-Za-z0-9._-]*" entry.id != null
      && (entry.path or null) == "${entry.id}.zip"
      && builtins.isString (entry.url or null)
      && lib.hasPrefix "https://" entry.url
      && builtins.isString (entry.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" entry.hash != null
      && builtins.isList (entry.mirrors or null)
      && builtins.all builtins.isString entry.mirrors
      && builtins.isAttrs (data.native.metadata.${entry.id} or null)
      && builtins.isList (data.native.modules.${entry.id} or null)
    ) entries
    && builtins.length (lib.unique (map (entry: entry.path) entries)) == builtins.length entries
    &&
      builtins.sort builtins.lessThan (map (entry: entry.id) entries)
      == builtins.sort builtins.lessThan (map (selected: selected.id) data.selection.extensions);
in
{
  purifier = "inkscape";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "Inkscape lock is missing, malformed, or stale; run inkscape-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
