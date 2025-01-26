from pathlib import Path


def relative_path(p1: Path, p2: Path) -> str:
    """Identify the path of p1 relative to the file p2."""
    assert p1.exists()  # Note: the second path does not need to exist
    if p1.parent == p2.parent:
        return f"./{p1.name}"
    _p1 = p1.parts
    _p2 = p2.parts
    return next(
        (f"{'../..' + ''.join(f'/{p}' for p in _p1[i:])}" for i in range(len(_p1), 1, -1) if _p1[:i] == _p2[:i]),
        "",
    )


def get_path(p1: str, base: Path | None = None) -> Path:
    """Get the full path of p1, which could be relative to base."""
    if base is None:
        base = Path.cwd()
    if Path(p1).exists():
        return Path(p1).resolve()
    p = (base / Path(p1)).resolve()
    if p.exists():
        return p
    raise Exception(f"File {p1} relative to {base} not found") from None
