import os

__version__ = "1.0.0"


def data_dir() -> str:
    """Return the crux data directory (for DB, config, logs).

    Uses %APPDATA%/crux on Windows, ~/.crux on Unix.
    """
    if os.name == "nt":
        appdata = os.environ.get(
            "APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        )
        return os.path.join(appdata, "crux")
    return os.path.join(os.path.expanduser("~"), ".crux")
