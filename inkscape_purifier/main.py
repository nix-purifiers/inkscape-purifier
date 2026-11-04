"""INKSCAPE's normal application workflow with a frozen native extension profile."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("INKSCAPE addon repositories must use public HTTPS URLs")
    return url


def selection(project):
    import re

    value = json.loads((project / "inkscape-purifier.json").read_text())
    if set(value) != {"extensions"} or not isinstance(value["extensions"], list):
        raise ValueError("inkscape-purifier.json needs an extensions list")
    ids = []
    for selected in value["extensions"]:
        if not isinstance(selected, dict) or set(selected) != {"id", "query"}:
            raise ValueError("extensions need native id and gallery query")
        if not isinstance(selected["id"], str) or not re.fullmatch(
            "[A-Za-z0-9][A-Za-z0-9._-]*", selected["id"]
        ):
            raise ValueError("invalid native extension ID")
        if not isinstance(selected["query"], str) or not selected["query"].strip():
            raise ValueError("native gallery query must be nonempty")
        ids.append(selected["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate native extension IDs")
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "inkscape-purifier.json").exists() or (
            parent / "inkscape-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "inkscape":
        raise ValueError("unsupported INKSCAPE lock")
    if data.get("sdk") != os.environ["INKSCAPE_PURIFIER_SDK"]:
        raise ValueError("INKSCAPE SDK changed; run inkscape-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError(
            "extension selection changed; run inkscape-purifier lock --update"
        )
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["INKSCAPE_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def native_operation(root, request):
    request_file = root / "request.json"
    response = root / "response.json"
    request_file.write_text(json.dumps(request))
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("INKSCAPE_") and key not in {"INKSCAPE_PURIFIER_ORIGINAL"}:
            env.pop(key, None)
        if key in {
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "WAYLAND_SOCKET",
            "DBUS_SESSION_BUS_ADDRESS",
            "GTK_MODULES",
            "GTK_PATH",
        }:
            env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("INKSCAPE_PROFILE_DIR", "profile"),
    ]:
        directory = root / name
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    env.update(
        INKSCAPE_VERSION=os.environ["INKSCAPE_PURIFIER_NATIVE_VERSION"],
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=str(root / "python-cache"),
    )
    run(
        [
            os.environ["INKSCAPE_PURIFIER_PYTHON_SDK"] + "/bin/python3",
            os.environ["INKSCAPE_PURIFIER_NATIVE"] + "/inkscape_purifier_helper.py",
            str(request_file),
            str(response),
        ],
        env=env,
        stdout=sys.stderr,
    )
    return json.loads(response.read_text())


def prefetch(url):
    return json.loads(
        run(
            ["nix", "store", "prefetch-file", "--json", public_url(url)],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )


def capture(project, lock):
    requested = selection(project)
    with tempfile.TemporaryDirectory(prefix="inkscape-purifier-") as temporary:
        root = Path(temporary)
        native = native_operation(
            root,
            {
                "action": "capture",
                "extensions": requested["extensions"],
                "root": str(root / "capture"),
            },
        )
        entries = []
        for entry in native["entries"]:
            fetched = prefetch(entry["url"])

            if (
                hashlib.sha256(Path(fetched["storePath"]).read_bytes()).hexdigest()
                != entry["bytesSha256"]
            ):
                raise ValueError(
                    "Nix archive differs from the original Inkscape download"
                )
            entries.append(
                {key: value for key, value in entry.items() if key != "bytesSha256"}
                | {"hash": fetched["hash"], "mirrors": []}
            )
        data = {
            "version": 1,
            "purifier": "inkscape",
            "sdk": os.environ["INKSCAPE_PURIFIER_SDK"],
            "selection": requested,
            "entries": entries,
            "native": {"metadata": native["metadata"], "modules": native["modules"]},
        }
        candidate = root / "inkscape-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def prepared_environment(project, lock):
    data = validate(project, lock)
    state = project / ".inkscape-purifier"
    identity = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    roots = state / "environments"
    roots.mkdir(parents=True, exist_ok=True)
    environment = realize(project, lock, out_link=roots / identity)
    alias = state / "environment"
    if alias.exists() and not alias.is_symlink():
        raise ValueError("unexpected file at the managed Inkscape environment link")
    with tempfile.TemporaryDirectory(dir=state) as temporary:
        link = Path(temporary) / "environment"
        link.symlink_to(environment)
        os.replace(link, alias)
    return state, environment


def native_exec(project, lock, arguments, command="inkscape"):
    executable = Path(os.environ["INKSCAPE_PURIFIER_ORIGINAL"]) / "bin/inkscape"
    if not lock.exists():
        print(
            "warning: no Inkscape purifier lock; using ordinary, impure extension resolution",
            file=sys.stderr,
        )
        os.execve(executable, [str(executable), *arguments], os.environ.copy())
    state, environment = prepared_environment(project, lock)
    sys.path.insert(0, os.environ["INKSCAPE_PURIFIER_NATIVE"])
    from inkscape_purifier_prepare import prepare

    env = prepare(
        os.environ.copy(),
        state / "gui",
        environment,
        os.environ["INKSCAPE_PURIFIER_LOCKED_SDK"],
        os.environ["INKSCAPE_PURIFIER_PYTHON_SDK"],
        os.environ["INKSCAPE_PURIFIER_CACHE"],
    )
    executable = Path(os.environ["INKSCAPE_PURIFIER_LOCKED_SDK"]) / "bin/inkscape"
    identity = hashlib.sha256(
        (str(state) + "\0" + str(environment)).encode()
    ).hexdigest()[:24]
    if any(
        argument == "--app-id-tag" or argument.startswith("--app-id-tag=")
        for argument in arguments
    ):
        raise ValueError("locked Inkscape manages its instance ID; remove --app-id-tag")
    os.execve(
        executable,
        [str(executable), "--app-id-tag=purifier-" + identity, *arguments],
        env,
    )


def main():
    if os.environ.get("INKSCAPE_PURIFIER_COMMAND") not in {None, "inkscape-purifier"}:
        project = project_path(os.environ.get("INKSCAPE_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get(
                "INKSCAPE_PURIFIER_LOCK", project / "inkscape-purifier.lock.json"
            )
        ).resolve()
        native_exec(
            project, lock, sys.argv[1:], os.environ["INKSCAPE_PURIFIER_COMMAND"]
        )
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    scripted = sub.add_parser("run")
    scripted.add_argument("script")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("INKSCAPE_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get(
            "INKSCAPE_PURIFIER_LOCK", project / "inkscape-purifier.lock.json"
        )
    ).resolve()
    if args.action == "run":
        state, environment = prepared_environment(project, lock)
        sys.path.insert(0, os.environ["INKSCAPE_PURIFIER_NATIVE"])
        from inkscape_purifier_run_project import run_project

        script = (project / args.script).resolve()
        raise SystemExit(
            run_project(
                project,
                script,
                state / "run",
                environment,
                os.environ["INKSCAPE_PURIFIER_LOCKED_SDK"],
                os.environ["INKSCAPE_PURIFIER_PYTHON_SDK"],
                os.environ["INKSCAPE_PURIFIER_CACHE"],
                os.environ["INKSCAPE_PURIFIER_FONTS"],
                os.environ["INKSCAPE_PURIFIER_XVFB"],
                os.environ["INKSCAPE_PURIFIER_DBUS"],
                project / "output",
            )
        )
    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("INKSCAPE_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "inkscape-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"inkscape-purifier: {error}", file=sys.stderr)
        sys.exit(1)
