"""inkpost — turn a post into hand-drawn diagrams (d2 + TALA, sketch mode).

this package is a thin console-script wrapper. the real modules (config,
planner, renderer, presets, patterns, cli, server) stay flat, exactly as they
are in the repo, and are found at runtime:

  * repo checkout / editable install -> they sit one directory up from here
  * installed wheel                  -> they are shipped inside inkpost/_impl/

whichever it is, that directory goes on sys.path once, so `import config`
keeps meaning what it has always meant and no module needed editing.

    inkpost          -> cli.main()
    inkpost-serve    -> server.serve()   (http://127.0.0.1:8788)
"""
import os
import sys

__version__ = "0.1.0"
__all__ = ["main", "serve", "impl_dir", "__version__"]

_HERE = os.path.dirname(os.path.abspath(__file__))
_BUNDLED = os.path.join(_HERE, "_impl")


def impl_dir():
    """-> the directory holding config.py, or None if it cannot be found."""
    for cand in (_BUNDLED, os.path.dirname(_HERE)):
        if os.path.isfile(os.path.join(cand, "config.py")):
            return cand
    return None


IMPL_DIR = impl_dir()
_ready = False


def _home():
    """~/.inkpost, or $INKPOST_HOME. only used by an installed copy."""
    h = (os.environ.get("INKPOST_HOME") or "").strip() or os.path.join("~", ".inkpost")
    return os.path.abspath(os.path.expanduser(h))


def _relocate(config):
    """an installed wheel lives in site-packages (and a uvx env is disposable),
    so nothing may be written next to the code. runs/, the render cache and the
    .env move under ~/.inkpost. a repo checkout is left completely alone.

    anything config.py resolves for itself — an env var, a user config file —
    already points outside the package and is not touched.
    """
    home = _home()
    for attr, target in (("RUNS_DIR", os.path.join(home, "runs")),
                         ("CACHE_DIR", os.path.join(home, "cache", "renders"))):
        cur = getattr(config, attr, "")
        if isinstance(cur, str) and os.path.abspath(cur).startswith(IMPL_DIR):
            setattr(config, attr, target)

    env = getattr(config, "ENV_FILE", "")
    if isinstance(env, str) and os.path.abspath(env).startswith(IMPL_DIR) \
            and not os.path.exists(env):
        try:
            local = os.path.join(os.getcwd(), ".env")
        except OSError:                                   # cwd was deleted
            local = ""
        config.ENV_FILE = local if local and os.path.exists(local) \
            else os.path.join(home, ".env")


def _bootstrap():
    """put the impl directory on sys.path exactly once, before anything that
    reads config into a module global gets imported."""
    global _ready
    if _ready:
        return
    if IMPL_DIR is None:
        raise SystemExit(
            "inkpost: cannot find its own modules (looked in %s and %s). "
            "a broken install — try `pip install --force-reinstall inkpost`."
            % (_BUNDLED, os.path.dirname(_HERE)))
    if IMPL_DIR not in sys.path:
        sys.path.insert(0, IMPL_DIR)
    import config                                          # noqa: E402
    if IMPL_DIR == _BUNDLED:
        _relocate(config)
    _ready = True


def main(argv=None):
    """the `inkpost` command."""
    _bootstrap()
    import cli                                             # noqa: E402
    try:
        return cli.main(argv)
    except KeyboardInterrupt:
        sys.stderr.write("\n  stopped.\n")
        raise SystemExit(130)


def serve(host=None, port=None):
    """the `inkpost-serve` command — http on 127.0.0.1:8788."""
    _bootstrap()
    import config                                          # noqa: E402
    import server                                          # noqa: E402
    return server.serve(config.HOST if host is None else host,
                        config.PORT if port is None else port)
