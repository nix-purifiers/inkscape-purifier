from pathlib import Path


def edit(name, old, new, count=1):
    p = Path(name)
    s = p.read_text()
    assert s.count(old) == count, (name, old, s.count(old))
    p.write_text(s.replace(old, new))


signature = "gchar *_get_path(Domain domain, Type type, char const *filename, char const *extra=nullptr)\n{"
edit(
    "src/io/resource.cpp",
    signature,
    signature
    + """
    if (type == EXTENSIONS && (domain == USER || domain == SHARED)) {
        auto const locked = g_getenv("INKSCAPE_PURIFIER_EXTENSIONS");
        if (locked && *locked) {
            return g_build_filename(locked, filename, extra, nullptr);
        }
    }
""",
)
path = "share/extensions/other/inkman/inkman/target.py"
for method, count in [
    ("def _install(self, filename, info):", 2),
    ("def _uninstall(self, info, json_file):", 2),
    ("def write_file(self, source, source_name=None, extra=None):", 1),
    ("def remove_file(self, filename):", 1),
    ("def pip_install(self, filename):", 1),
    ("def pip_uninstall(self, name):", 1),
]:
    edit(
        path,
        "    " + method,
        "    "
        + method
        + """
        if os.environ.get("INKSCAPE_PURIFIER_EXTENSIONS") and self.category == "extension":
            raise RuntimeError("Inkscape extensions are locked; run inkscape-purifier lock --update")
""",
        count,
    )
edit(
    path,
    "    def is_writable(self):",
    """    def is_writable(self):
        if os.environ.get("INKSCAPE_PURIFIER_EXTENSIONS") and self.category == "extension":
            return False
""",
)
path = "share/extensions/other/inkman/inkman/backfoot.py"
edit(
    path,
    "def update_pip_package(package):",
    """def update_pip_package(package):
    if os.environ.get("INKSCAPE_PURIFIER_EXTENSIONS"):
        raise RuntimeError("Inkscape extension manager is locked; run inkscape-purifier lock --update")
""",
)
path = "src/extension/implementation/script.cpp"
edit(
    path,
    "    // 1. Check preferences for an override.",
    """    // Locked Python extensions use the provider interpreter, independently of preferences.
    if (g_getenv("INKSCAPE_PURIFIER_EXTENSIONS") && interpNameArg == "python") {
        auto const pinned = g_getenv("INKSCAPE_PURIFIER_PYTHON");
        return pinned && *pinned ? std::string(pinned) : interp->second.defaultvals.front();
    }

    // 1. Check preferences for an override.""",
)

edit(
    "share/extensions/other/inkman/inkman/target.py",
    "        self.path = os.path.join(INKSCAPE_PROFILE, path)",
    """        self.path = os.path.join(INKSCAPE_PROFILE, path)
        if self.category == "extension" and os.environ.get("INKSCAPE_PURIFIER_EXTENSIONS"):
            self.path = os.environ["INKSCAPE_PURIFIER_EXTENSIONS"]""",
)
