"""Python module for working with json5 files."""

import codecs
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyjson5 as json5
from jsonpath_ng.ext import parse
from pyjson5 import Json5Exception, Json5IllegalCharacter

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


def get_pos(txt: str, start: str = "near ", end: str = ",") -> int:
    pos0 = txt.find(start)
    assert pos0 >= 0, f"String {start} not found in {txt}"
    pos0 += 5
    pos1 = txt.find(end, pos0)
    assert pos1 >= 0, f"String {end} not found in {txt} after position {pos0}"
    return int(txt[pos0:pos1])


def json5_check(js5: dict[str, Any]) -> bool:
    """Check whether the dict js5 can be interpreted as Json5. Wrapper function."""
    return json5.encode_noop(js5)


def json5_write(  # noqa: C901, PLR0915
    js5: dict[str, Any],
    file: Path | str,
    *,
    indent: int = 3,
    compact: bool = True,
) -> None:
    """Use pyjson5 to print the json5 code to file, optionally using indenting the code to make it human-readable.

    Args:
        file (Path): Path (file) object. Is overwritten if it exists.
        indent (int) = 3: indentation length. Raw dump if set to -1
        compact (bool) = True: compact file writing, i.e. try to keep keys unquoted and avoid escapes
    """

    def _unescape(chars: str) -> str:
        """Try to unescape chars. If that results in a valid Json5 value we keep the unescaped version."""
        if len(chars) and chars[0] in ("[", "{"):
            pre = chars[0]
            chars = chars[1:]
        else:
            pre = ""
        if len(chars) and chars[-1] in ("]", "}", ","):
            post = chars[-1]
            chars = chars[:-1]
        else:
            post = ""

        unescaped = codecs.decode(chars, "unicode-escape")
        try:
            json5.decode("{ key : " + unescaped + "}")
        except Json5Exception:
            return pre + chars + post  # need to keep the escaping to have valid Json5
        else:  # unescaped this is still valid Json5
            return pre + unescaped + post

    def _pretty_print(chars: str) -> None:  # noqa: C901
        nonlocal fp, level, indent, _list, _collect

        # first all actions with explicit fp.write
        if chars == ":":
            if compact:
                _c = _collect.strip()
                no_quote = _c.strip('"').strip("'").strip('"').strip("'")
                try:
                    json5.decode("{" + no_quote + " : 'dummy'}")
                except Json5Exception:
                    _collect += ": "
                else:
                    _collect = f"{no_quote}: "
                _ = fp.write(_collect)
                _collect = ""
        elif chars == "{":
            level += 1
            _collect += "{\n" + " " * (level * indent)
        elif chars == "," and _list == 0:
            _collect += ",\n" + " " * (level * indent)
        else:  # default
            _collect += chars
        # level and _list handling
        if chars == "}":
            level -= 1
        elif chars == "[":
            _list += 1
        elif chars == "]":
            _list -= 1
        # write to file and reset _collect
        if chars in {"{", "}", "[", "]", ","}:
            _ = fp.write(_unescape(_collect))
            _collect = ""

    assert json5.encode_noop(js5), f"Python object {js5} is not serializable as Json5"
    if indent == -1:  # just dump it no pretty print, Json5 features, ...
        txt = json5.encode(js5, quotationmark="'")
        with Path.open(Path(file), "w") as fp:
            _ = fp.write(txt)

    elif indent >= 0:  # pretty-print and other features are taken into account
        level: int = 0
        _list: int = 0
        _collect: str = ""
        with Path.open(Path(file), "w") as fp:
            _ = json5.encode_callback(js5, _pretty_print, supply_bytes=False, quotationmark="'")


def json5_find_identifier_start(txt: str, pos: int) -> int:
    """Find the position of the start of the identifier in txt going backwards from pos."""
    p: int = pos - 1
    while True:
        if p < 0:
            return 0
        if txt[p] in (",", "{", "}", "[", "]", ":"):
            return p + 1
        p -= 1


def json5_try_correct(txt: str, pos: int) -> tuple[bool, str]:
    """Try to repair the json5 illegal character found at pos in txt.

    1. Check whether pos points to a key and set the key in quotation marks.
    2. Check whether pos points to an illegal comment marker and replace with //
    """
    success: bool = False
    if txt[pos] == "#":  # python type comment
        txt = f"{txt[:pos]}//{txt[pos + 1 :]}"
        success = True
    else:
        m = re.search(":", txt[pos:])
        if m is None:
            logger.warning(f"No key found at {txt[pos : pos + 15]}...")
        else:
            key = txt[pos : pos + m.start()].strip()
            m2 = re.search(r"\s|,|\{|\}|\[|\]", key)
            if m2 is not None:
                logger.warning(f"The key candidate {key} is not a Json5 key")
            else:
                txt = f"{txt[:pos]} '{key}' : {txt[pos + m.end() :]}"
                success = True
    return (success, txt)


def json5_read(file: Path | str, *, save: int = 0) -> dict[str, Any]:  # noqa: C901, PLR0912
    """Read the Json5 file.
    If key or comment errors are encountered they are tried fixed 'en route'.
    save: 0: do not save, 1: save if changed, 2: save in any case. Overwrite file when saving.
    """

    def get_line(txt: str, pos: int) -> int:
        """Get the line number related to pos in txt, counting newline.
        If no more line breaks are found, the current line count is returned.
        """
        _p = 0
        line = 0
        while True:
            _p = txt.find("\n", _p) + 1
            if _p > pos or _p <= 0:
                return line + 1
            line += 1

    with Path.open(Path(file), "r") as fp:
        txt = fp.read()
    num_warn = 0
    while True:
        try:
            js5 = json5.decode(txt, maxdepth=-1)
        except Json5Exception as err:
            if err.__class__ is Json5IllegalCharacter:
                num_warn += 1
                pos = get_pos(str(err)) - 1
                _line = get_line(txt, pos)
                if err.args[0].startswith("Expected b'comma'"):
                    raise ValueError(f"Missing comma? in {file}, line {_line} at {txt[pos : pos + 20]}") from err
                if err.args[0].startswith("Expected b'IdentifierStart'"):
                    success, txt = json5_try_correct(txt, pos)
                    if not success:
                        raise ValueError(
                            f"{file} Unrepairable identifier in {txt[pos : pos + 15]}, line {_line}"
                        ) from err
                elif err.args[0].startswith("Expected b'colon'"):  # the illegal character is i middle of the key!
                    pos = json5_find_identifier_start(txt, pos)
                    success, txt = json5_try_correct(txt, pos)
                    if not success:
                        raise ValueError(f"{file} Unrepairable key in {txt[pos : pos + 15]}, line {_line}") from err

                else:
                    raise ValueError(f"Unhandled illegal character problem in {file}, line {_line}.") from err
            else:
                raise ValueError(f"Unhandled problem in Json5 file {file}: {err.args[0]}") from err
        else:
            break
    if save == 0 and num_warn > 0:
        logger.warning(f"Decoding the file {file}, {num_warn} illegal characters were detected. Not saved.")
    elif (save == 1 and num_warn > 0) or save == 2:  # noqa: PLR2004
        logger.warning(f"Decoding the file {file}, {num_warn} illegal characters were detected. File re-saved.")
        json5_write(js5, file, indent=3, compact=True)
    return js5


def json5_path(
    js5: dict[str, Any],
    path: str,
    typ: type | None = None,
) -> Any:  # noqa: ANN401
    """Evaluate a JsonPath expression on the Json5 code and return the result.

    Syntax see `RFC9535 <https://datatracker.ietf.org/doc/html/rfc9535>`_
    and `jsonpath-ng (used here) <https://pypi.org/project/jsonpath-ng/>`_

    * $: root node identifier (Section 2.2)
    * @: current node identifier (Section 2.3.5) (valid only within filter selectors)
    * [<selectors>]: child segment (Section 2.5.1): selects zero or more children of a node
    * .name: shorthand for ['name']
    * .*: shorthand for [*]
    * ..⁠[<selectors>]: descendant segment (Section 2.5.2): selects zero or more descendants of a node
    * ..name: shorthand for ..['name']
    * ..*: shorthand for ..[*]
    * 'name': name selector (Section 2.3.1): selects a named child of an object
    * *: wildcard selector (Section 2.3.2): selects all children of a node
    * i: (int) index selector (Section 2.3.3): selects an indexed child of an array (from 0)
    * 0:100:5: array slice selector (Section 2.3.4): start:end:step for arrays
    * ?<logical-expr>: filter selector (Section 2.3.5): selects particular children using a logical expression
    * length(@.foo): function extension (Section 2.4): invokes a function in a filter expression

    Args:
        js5 (dict): a Json5 conformant dict
        path (str): path expression as string.
        typ (type)=None: optional specification of the expected type to find
    """
    compiled = parse(path)
    data = compiled.find(js5)
    val = None
    if not data:  # not found
        return None
    val = data[0].value if len(data) == 1 else [x.value for x in data]
    if val is not None and typ is not None and not isinstance(val, typ):
        try:  # try to convert
            val = typ(val)
        except ValueError:
            raise ValueError(f"{path} matches, but type {typ} does not match {type(val)} in {js5}.") from None
    return val


def json5_update(
    js5: dict[str, Any],
    keys: Sequence[str],
    data: Any,  # noqa: ANN401
) -> None:
    """Append data to the js_py dict at the path pointed to by keys.
    So far this is a minimum implementation for adding data.

    Args:
        js5 (dict): A Json5 conformant dict
        keys (Sequence): Sequence of keys. All keys down to the place where to update the dict shall be included
        data (Any): the data to be added/updated. Dicts are updated, lists are appended
    """
    value: Any = None
    for i, k in enumerate(keys):
        if k not in js5:
            for j in range(len(keys) - 1, i - 1, -1):
                data = {keys[j]: data}
            break
        parent = js5
        value = js5[k]
    if isinstance(value, list):
        value.append(data)
    elif isinstance(value, dict):
        value.update(data)
    elif isinstance(parent, dict):  # update the parent dict (replace a value)
        parent.update({k: data})
    else:
        raise TypeError(f"Unknown type of path: {js5}")
