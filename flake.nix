{
  description = "inkscape with locked, Nix-resolved add-ons";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        inkscape-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (
        system:
        let
          p = (pkgsFor system).inkscape-purifier;
        in
        {
          default = p.cli;
          inkscape = p.original;
          xvfb = (pkgsFor system).xvfb-run;
          gui-test-env =
            let
              pkgs = pkgsFor system;
            in
            pkgs.runCommand "purifier-gui-test-environment" { } ''
              mkdir -p "$out/bin"
              ln -s ${pkgs.lib.getBin pkgs.dbus}/bin/dbus-run-session "$out/bin/dbus-run-session"
              ln -s ${pkgs.lib.getBin pkgs.dbus}/bin/dbus-daemon "$out/bin/dbus-daemon"
              ln -s ${
                pkgs.makeFontsConf {
                  fontDirectories = [
                    pkgs.dejavu_fonts
                    pkgs.noto-fonts
                  ];
                }
              } "$out/fonts.conf"
            '';
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/inkscape-purifier";
        };
      });
      lib.inkscape-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = (pkgsFor system).inkscape-purifier;
          build = p.buildInkscapeProject {
            src = ./examples/minimal;
            doCheck = true;
            checkCommand = ''test -s "$out/drawing.svg"'';
          };
        in
        {
          cli = p.cli;
          resources = import ./tests/resource-projections.nix {
            pkgs = pkgsFor system;
            build = p.buildInkscapeProject;
          };
          inherit (build.packages) environment project;
          release = build.release;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
