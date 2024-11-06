from pathlib import Path
import os

            
def relative_path( p1:Path, p2:Path) -> str:
    """Identify the path of p1 relative to the file p2."""
    assert p1.exists()
    assert p2.exists()
    if p1.parent == p2.parent:
        return './'+p1.name
    else:
        _p1 = p1.parts
        _p2 = p2.parts
        for i in range(len(_p1),1,-1):    
            if _p1[:i] == _p2[:i]:
                return f"{ '../..' +''.join('/'+p for p in _p1[i:])}"
                break

def get_path( p1:str, base:Path = Path.cwd()) -> Path:
    """Get the full path of p1, which could be relative to base."""
    if Path(p1).exists():
        return Path(p1).resolve()
    else:
        p = (base / Path(p1)).resolve()
        if p.exists():
            return p
        else:
            raise Exception(f"File {p1} relative to {base} not found") from None