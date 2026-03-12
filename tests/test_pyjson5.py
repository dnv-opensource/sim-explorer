import logging
import time
from pathlib import Path
from typing import Any

import pytest

from sim_explorer.utils.json5 import json5_check, json5_read, json5_write

# from pyjson5 import Json5Exception, Json5IllegalCharacter

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


def test_read_results():
    def do_file(file: Path):
        t0 = time.time()
        js5 = json5_read(file)
        logger.info(f"Reading {file.name} in {(time.time() - t0)} seconds")
        print(type(js5), js5)
        assert isinstance(js5, dict)
        assert "header" in js5
        for k in js5:
            if k != "header":
                assert isinstance(float(k), float)
        json5_write(js5, Path(file.name), indent=3)  # write to test_working_directory

    do_file(Path(__file__).parent / "data" / "BouncingBall3D" / "test_results")
    do_file(Path(__file__).parent / "data" / "BouncingBall3D" / "base.js5")
    do_file(Path(__file__).parent / "data" / "Oscillator" / "forced.js5")


def test_read_cases():
    def do_file(file: Path):
        t0 = time.time()
        js5 = json5_read(file)

        assert isinstance(js5, dict)
        assert "header" in js5
        assert "base" in js5
        logger.info(f"Reading {file.name} in {time.time() - t0} seconds")
        assert json5_check(js5), f"Object {js5} is not serializable as Json5"
        json5_write(js5, file.name, indent=3)  # write to test_working_directory

    do_file(Path(__file__).parent / "data" / "BouncingBall0" / "BouncingBall.cases")
    do_file(Path(__file__).parent / "data" / "BouncingBall3D" / "BouncingBall3D.cases")
    do_file(Path(__file__).parent / "data" / "Oscillator" / "ForcedOscillator.cases")


def single_file(f: Path, save: int):
    js5 = json5_read(f, save=save)
    if json5_check(js5):
        logger.info(f"File {f} ok")
    else:
        logger.error(f"File {f} is not ok")
    return js5


def repair_all_json5(folder: Path, do_change: int):
    """Check and repair all Json5 files in folder and subfolders.
    This is related to the fact that in the first versions of sim-explorer an extended dialect of Json5 was used.
    """
    for f in folder.glob("**/*"):
        if f.is_file() and f.suffix in (".js5", ".cases"):
            js5 = single_file(f, save=do_change)
    # additional files with other suffix (for easier usage as test cases)
    for f2 in ("data/BouncingBall3D/test_case", "data/BouncingBall3D/test_results"):
        f = Path(__file__).parent / f2
        js5 = json5_read(f, save=0)  # we do not change these as the comments will vanish
        _ = json5_check(js5)
        logger.info(f"File {f} ok")


@pytest.fixture(scope="session")
def do_change() -> int:
    return 0


def test_all_json5(do_change: int) -> None:
    repair_all_json5(Path(__file__).parent, do_change=do_change)


"""
{
    hello: "world",
    _: "underscore",
    $: "dollar sign",
    one1: "numerals",
    _$_: "multiple symbols",
    $_$hello123world_$_: "mixed"
}
"""


def test_write():
    js5: dict[str, str | int | float | list[Any] | dict[str, Any]] = {
        "Hello": "World",
        "t@his": ["is", "a", "simple", "test"],
        "h[0]w": "this dict",
        "i:s": ["re>resented in Json", 5],
        "int": 99,
        "float": 99.99,
        "positiveInfinity": "Infinity",
        "negativeInfinity": "-Infinity",
        "notANumber": "NaN",
    }
    # print("AS STRING", json5.dumps(js5, quotationmark="'", quote_keys=False))
    json5_write(js5, "test_write.js5", indent=3)
    txt = Path("test_write.js5").read_text()
    expected = """
{
   Hello: 'World',
   't@his': ['is','a','simple','test'],
   'h[0]w': 'this dict',
   'i:s': ['re>resented in Json',5],
   int: 99,
   float: 99.99,
   positiveInfinity: 'Infinity',
   negativeInfinity: '-Infinity',
   notANumber: 'NaN'}"""
    assert txt != expected, f"EXPECTED:\n{expected}\nFOUND:\n{txt}"
    # print(txt)
    _ = json5_read("test_write.js5")


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__, "--show", "True"])
    assert retcode == 0, f"Non-zero return code {retcode}"
    import os

    os.chdir(Path(__file__).parent.absolute() / "test_working_directory")
    # repair_all_json5( Path(__file__).parent, do_change = True)
    # test_read_results()
    # test_read_cases()
    # test_all_json5( do_change=0)
    # single_file(Path(__file__).parent / 'data' / 'BouncingBall3D' / 'test_case', 0)
    # test_write()
