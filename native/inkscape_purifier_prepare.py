"""Activate an immutable extension virtual environment and writable native profile."""

from pathlib import Path


def prepare(env, state, environment, sdk, python_sdk, cache):
    state = Path(state).resolve()
    environment = Path(environment).resolve()
    sdk = Path(sdk).resolve()
    python_sdk = Path(python_sdk).resolve()
    profile = state / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    env = env.copy()
    for key in [
        "INKSCAPE_DATADIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "INKSCAPE_PROFILE_DIR",
        "INKSCAPE_EXTENSIONS_DIR",
    ]:
        env.pop(key, None)
    env.update(
        INKSCAPE_PROFILE_DIR=str(profile),
        INKSCAPE_EXTENSIONS_DIR=str(environment / "extensions"),
        INKSCAPE_PURIFIER_EXTENSIONS=str(environment / "extensions"),
        INKSCAPE_DATADIR=str(sdk / "share"),
        INKSCAPE_PURIFIER_PYTHON=str(environment / "venv/bin/python3"),
        VIRTUAL_ENV=str(environment / "venv"),
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=str(cache),
        PYTHONPATH=":".join(
            [
                str(sdk / "share/inkscape/extensions/inkman/inkman"),
                str(sdk / "share/inkscape/extensions"),
                str(next((python_sdk / "lib").glob("python*/site-packages"))),
            ]
        ),
        PATH=str(environment / "venv/bin")
        + ":"
        + str(sdk / "bin")
        + ":"
        + env.get("PATH", ""),
    )
    return env
