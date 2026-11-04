{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  original = pkgs.inkscape;
  pythonSdk = builtins.head (
    builtins.filter (
      p: pkgs.lib.hasPrefix "python3-" p.name && pkgs.lib.hasSuffix "-env" p.name
    ) scope.original.buildInputs
  );
  nativeVersion = pkgs.lib.versions.majorMinor scope.original.version;
  lockedSdk = scope.original.overrideAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      ${pkgs.python3}/bin/python ${../native/patch_sdk.py}
    '';
  });
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  readLock = import ./read-lock.nix { inherit (pkgs) lib; };
  environment = scope.callPackage ./environment.nix { };
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildInkscapeProject = scope.callPackage ./build-project.nix { };
  emptyCache = pkgs.runCommand "inkscape-immutable-python-cache" { } "mkdir -p $out";
  fontConfig = pkgs.makeFontsConf {
    fontDirectories = [
      pkgs.dejavu_fonts
      pkgs.noto-fonts
    ];
  };
  sdk = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      native = builtins.listToAttrs (
        map
          (path: {
            name = pkgs.lib.removePrefix (toString ../native + "/") (toString path);
            value = builtins.hashFile "sha256" path;
          })
          (
            builtins.filter (path: pkgs.lib.hasSuffix ".py" (toString path)) (
              pkgs.lib.filesystem.listFilesRecursive ../native
            )
          )
      );
      providers = pkgs.lib.genAttrs [ "scope.nix" "environment.nix" ] (
        name: builtins.hashFile "sha256" (./. + ("/" + name))
      );
    }
  );
})
