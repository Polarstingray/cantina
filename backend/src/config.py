'''
config.py
    Central runtime configuration, read once from the environment so the rest
    of the app never reaches for os.environ or hardcodes a path/port.

    CANTINA_DATA_DIR  directory holding the .bin data files (and, after the
                      sqlite migration, the database). Defaults to this source
                      directory so existing installs and the committed sample
                      data keep working with no env set. Point it at something
                      like ~/cantina-data so the data survives git operations
                      and is easy to back up.
    CANTINA_HOST      interface uvicorn binds. Default 0.0.0.0 for LAN access;
                      set 127.0.0.1 once a tunnel/reverse proxy is the entry point.
    CANTINA_PORT      port uvicorn binds. Default 8000.
'''

import os

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ.get("CANTINA_DATA_DIR") or _SRC_DIR
HOST = os.environ.get("CANTINA_HOST", "0.0.0.0")
PORT = int(os.environ.get("CANTINA_PORT", "8000"))

# Make sure the data directory exists before any module tries to write into it.
os.makedirs(DATA_DIR, exist_ok=True)


def data_path(filename: str) -> str :
    '''Absolute path to a data file inside DATA_DIR.'''
    return os.path.join(DATA_DIR, filename)
