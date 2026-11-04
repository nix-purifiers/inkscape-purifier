# inkscape-purifier

Use Inkscape with locked, Nix-resolved extensions.

## Quickstart

Enter a shell with the wrapper:

```sh
nix shell 'github:nix-purifiers/inkscape-purifier'
```

Create `inkscape-purifier.json` with an extension's gallery ID and search query:

```json
{
  "extensions": [
    {
      "id": "org.inkscape.extension.6851",
      "query": "RealScale"
    }
  ]
}
```

Capture the lock, then open your drawing:

```sh
inkscape-purifier lock --update
inkscape drawing.svg
```

The wrapper loads the selected extensions from the Nix store. Preferences and
application state remain writable in `.inkscape-purifier/gui/profile`. Python
extensions use an automatically activated, immutable virtual environment with
the SDK's `inkex` and Python libraries.

Without a lockfile, `inkscape` warns and delegates to ordinary Inkscape. A stale
or invalid lock fails with a repair message.

## Updating extensions

Edit the selection and recapture:

```sh
inkscape-purifier lock --update
```

The integration uses `inkman`'s native gallery search, compatibility checks,
downloader, INX parser and archive installer. It verifies that Nix fetched the
same bytes, then validates installation before replacing the previous lock.
`inkscape-purifier lock` preserves current pins; `prefetch` realizes the locked
environment.

Native extension installation, removal, pip operations and manager self-update
are frozen in locked sessions. The manager still shows the selected extensions.

## Scripted workflows

Inkscape's extension actions require its GTK application. Run a Python build
script with a private virtual display and session bus:

```sh
inkscape-purifier run build.py
```

The command activates the locked Python environment and SDK and preserves the
script's exit status. It uses a separate profile in `.inkscape-purifier/run`,
so scripted settings stay separate from the interactive profile. Ordinary
project networking remains available.

The included example calls RealScale through Inkscape's native action and
exports SVG. Edit `source.svg` and rerun:

```sh
cd examples/minimal
inkscape-purifier run build.py
```

## Nix builds

The overlay exposes `pkgs.inkscape-purifier.buildInkscapeProject`. It executes
`build.py` in the Nix sandbox with the same native SDK and private display.
`INKSCAPE_PURIFIER_OUTPUT` names the output directory. The builder provides
dependency, project, test and normalized release outputs.

```sh
inkscape-purifier build
inkscape-purifier bundle
```

## Scope

The pinned SDK is Inkscape 1.4.4. The current provider supports verified gallery
ZIP extensions compatible with Inkscape 1.4, using Python INX commands and the
SDK's libraries. Pip packages, additional Python dependencies, external tool
providers and other interpreter types need integrations.

Locked sessions fix user and shared extension paths and the Python interpreter,
including when saved preferences request different paths. Instances are named
by workspace and environment to avoid forwarding into an ordinary or older
session. Custom `--app-id-tag` overrides are unavailable while locked.

The wrapper controls extension resolution; it does not sandbox arbitrary
extension or project-script behavior. Native Inkscape actions can report errors
without a failing exit status, so builds should check their output.

Linux x86_64 and aarch64 are configured. Runtime verification currently runs
on x86_64. Typed projection interfaces are unsupported.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
