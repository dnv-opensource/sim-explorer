from pathlib import Path


def relative_path(p1: Path, p2: Path | None) -> str:
    """Identify the path of p1 relative to the file p2."""
    assert p1.exists()  # Note: the second path does not need to exist
    assert isinstance(p2, Path)
    if p1.parent == p2.parent:
        return "./" + p1.name
    else:
        _p1 = p1.parts
        _p2 = p2.parts
        for i in range(len(_p1), 1, -1):
            if _p1[:i] == _p2[:i]:
                return f"{ '../..' +''.join('/'+p for p in _p1[i:])}"
                break
    return ""


def get_path(p1: str, base: Path | None = None) -> Path:
    """Get the full path of p1, which could be relative to base."""
    if base is None:
        base = Path.cwd()
    if Path(p1).exists():
        return Path(p1).resolve()
    else:
        p = (base / Path(p1)).resolve()
        if p.exists():
            return p
        else:
            raise Exception(f"File {p1} relative to {base} not found") from None
