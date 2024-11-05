from __future__ import annotations

# from jsonpath_ng.ext.filter import Expression#, Filter
import os
import re
from pathlib import Path
from typing import Any

from jsonpath_ng.ext import parse  # type: ignore
from jsonpath_ng.jsonpath import DatumInContext  # type: ignore


class Json5Error(Exception):
    """Special error indicating that something was not conformant to json5 code."""

    pass


class Json5:
    """Work with json5 files (e.g. cases specification and results).

    * Read Json5 code from file, string or dict, representing the result internally as Python code (dict of dicts,lists,values)
    * Searching for elements using JsonPath expressions
    * Some Json manipulation methods
    * Write Json5 code to file

    Args:
        js5 (Path,str): Path to json5 file or json5 string
        auto (bool)=True: Determine whether running to_py automatically
        comments_eol (tuple)= ('//', '#') : tuple of end-of-line comment strings which shall be recognised
        comments_ml (tuple)= ('/*', "'''") : tuple of multi-line comment strings which shall be recognised.
          End of comment is always the reversed of the start of comment.
          Double-quote ml comments are also supported per default
    """

    __slots__ = ("comments", "comments_eol", "comments_ml", "js5", "js_py", "lines", "pos")

    def __init__(
        self,
        js5: str | os.PathLike[str] | dict,
        auto: bool | int = True,
        comments_eol: tuple[str, ...] = (
            "//",
            "#",
        ),
        comments_ml: tuple[str, ...] = ("/*", "'" * 3, '"' * 3),
        keys_unique: bool = True,
    ):
        self.pos = 0
        self.comments_eol = comments_eol
        self.comments_ml = comments_ml
        if isinstance(js5, dict):  # instantiation from dict
            assert self.check_valid_js(js5), f"{js5} is not a valid Json dict"
            self.js_py = js5
            self.js5 = ""
        else:  # instantiation from file
            try:
                if Path(js5).exists():
                    with open(Path(js5), "r") as file:  # read file into string
                        self.js5 = file.read()
            except Exception:
                pass
            if not hasattr(self, "js5"):  # file reading not succesfull
                if isinstance(js5, str):
                    self.js5 = js5
                else:
                    raise Json5Error(f"Invalid Json5 input {self.js5}") from None
            if self.js5[0] != "{":
                self.js5 = "{\n" + self.js5
            if self.js5[-1] != "}":
                self.js5 = self.js5 + "\n}"
            self.js5, self.lines = self._lines()  # map the lines first so that error messages work
            self.js5, self.comments = self._comments()
            self.js5, _ = self._newline()  # replace unnecessary LFs and return start position per line
            self.js_py = {}  # is replaced by the python json5 dict when to_py() is run
            if auto:
                self.js_py = self.to_py()

    def _msg(self, pre: str, num: int = 50, pos: int | None = None) -> str:
        """Construct an error message from pre and a citation from the raw json5 code.

        The citation is from 'pos' with 'num' characters.
        Used mostly for reporting reader errors.
        """
        if pos is None:
            pos = self.pos
        try:
            line, p = self._get_line_number(pos)
            return f"Json5 read error at {line}({p}): {pre}: {self.js5[pos : pos+num]}"
        except Json5Error as err:  # can happen when self.lines does not yet exist
            return f"Json5 read error at {pos}: {pre}: {self.js5[pos : pos+num]}: {err}"

    def _lines(self):
        """Map start positions of lines and replace all newline CR-LF combinations with single newline (LF)."""
        c = re.compile(r"\n\r|\r\n|\r|\n")
        pos = 0
        lines = [0]
        js = ""
        while True:
            s = c.search(self.js5[pos:])
            if s is None:
                return (js + self.js5[pos:], lines)
            js += self.js5[pos : pos + s.start()] + "\n"
            lines.append(len(js))  # register line start
            pos += s.end()

    def _newline(self):
        """Replace unnecessary line feeds with spaces and return list of start position per line."""
        qt1 = 0  # single quote state
        qt2 = 0  # double quote state
        c = re.compile(r'"|\'|\n\r|\r\n|\r|\n')
        pos = 0
        lines = [0]
        js = ""
        while True:
            s = c.search(self.js5[pos:])
            if s is None:
                if qt1 + qt2 != 0:
                    self._msg("Non-matching quotes detected")
                return (js + self.js5[pos:], lines)

            js += self.js5[pos : pos + s.start()]
            if s.group() == '"' and not qt1:
                qt2 = 1 - qt2
                js += s.group()
            elif s.group() == "'" and not qt2:
                qt1 = 1 - qt1
                js += s.group()
            else:
                lines.append(pos + s.end())  # register line start (also if within literal string)
                if not (qt1 or qt2):  # we are not within a literal string
                    if s.group() in ("\n\r", "\r\n"):
                        js += "  "
                    elif s.group() in ("\r", "\n"):
                        js += " "
                else:  # within a literal string newlines are kept
                    js += s.group()
            pos += s.end()

    def _get_line_number(self, pos: int) -> tuple[int, int]:
        """Get the line number relative to position 'pos'.
        Returns both the row and column of 'pos' (1-based).
        """
        for i, p in enumerate(self.lines):  # line number (zero-based) and position at beginning of line
            if p > pos:  # read too far
                return i, pos - self.lines[i - 1] + 1
        return len(self.lines), pos - self.lines[-1] + 1

    def line(self, num: int) -> str:
        """Return the raw json5 line 'num'.

        Args:
            num (int): the line number of the line to retrieve (zero-based).
              'num' works here like python indexes, starting from 0 and also working with negative numbers!
        """
        L = len(self.lines)
        if num == -1 or num == L - 1:
            return self.js5[self.lines[-1] :].strip()
        elif -L + 1 < num < -1:
            return self.js5[L + num : L + num + 1]
        elif len(self.lines) > num - 1:
            return self.js5[self.lines[num] : self.lines[num + 1]].strip()
        else:
            return ""

    def _comments(self, js5: str = "") -> tuple[str, dict[int, str]]:
        """Take the raw json5 text 'js5' (default: self.js5) as input and replace comments with whitespace.

        Both comments_eol and comment_ml are taken into account as initialized.
        Leave the line breaks intact, so that line counting is not disturbed.
        Return the resulting 'cleaned' string and the comments dict
        """

        def _re(txt: str):
            return "".join("\\" + ch if ch in ("*",) else ch for ch in txt)

        _js5 = self.js5 if js5 == "" else js5
        comments = {}
        cq = re.compile(r"'([^']*)'")  #  single quotes
        cq2 = re.compile(r'"([^"]*)"')  # double quotes
        for cmt in self.comments_eol:  # handle end-of-line comments
            js5 = _js5
            _js5 = ""
            c = re.compile(r"" + cmt + ".*$", re.MULTILINE)  # eol comments
            pos = 0
            while True:
                s = c.search(js5[pos:])
                sq = cq.search(js5[pos:])
                sq2 = cq2.search(js5[pos:])
                # print("_COMMENTS", pos, s, sq, sq2)
                if s is None:
                    _js5 += js5[pos:]
                    break
                elif (sq is None or s.start() < sq.start() or s.start() > sq.end()) and (
                    sq2 is None or s.start() < sq2.start() or s.start() > sq2.end()
                ):
                    # no quote or comments starts before or after quote. Handle comment
                    comments.update({pos + s.start(): s.group()})
                    _js5 += js5[pos : pos + s.start()]
                    _js5 += " " * len(s.group())
                    pos += s.end()
                elif sq is not None and sq.start() < s.start() < sq.end():
                    # Comment sign within single quotes. Leave alone
                    _js5 += js5[pos : pos + sq.end()]
                    pos += sq.end()
                elif sq2 is not None and sq2.start() < s.start() < sq2.end():
                    # Comment sign within double quotes. Leave alone
                    _js5 += js5[pos : pos + sq2.end()]
                    pos += sq2.end()
                else:
                    raise Json5Error(f"Unhandled EOL-comment removal: {s}, {sq}, {sq2}")

        #                 if (
        #                     s is None
        #                     or (sq is not None and sq.end() < s.start())
        #                     or (sq2 is not None and sq2.end() < s.start())
        #                 ):
        #                     _js5 += js5[pos:]
        #                     break
        #                 if (s is not None and
        #                     (sq is None or sq.start() > s.start() or s.start() > sq.end()) and
        #                     (sq2 is None or sq2.start() > s.start() or s.start() > sq2.end())): # comment sign outside quotes
        #                     comments.update({pos + s.start(): s.group()})
        #                     _js5 += js5[pos : pos + s.start()]
        #                     _js5 += " " * len(s.group())
        #                     pos += s.end()
        #                 elif sq is not None:
        #                     _js5 += js5[pos : sq.end()]
        #                     pos += sq.end()
        #                 elif sq2 is not None:
        #                     _js5 += js5[pos : sq2.end()]
        #                     pos += sq2.end()
        #                 else:
        #                     raise Json5Error(f"Unresolved when removing comments {js5[pos:]}") from None

        for cmt in self.comments_ml:  # handle multi-line comments
            js5 = _js5
            _js5 = ""
            c1 = re.compile("" + _re(cmt))
            c2 = re.compile("" + _re(cmt[::-1]))
            pos = 0
            while True:
                s1 = c1.search(js5[pos:])
                sq = cq.search(js5[pos:])
                sq2 = cq2.search(js5[pos:])
                if s1 is None:
                    _js5 += js5[pos:]
                    break
                _js5 += js5[pos : pos + s1.start()]
                pos += pos + s1.start()
                s2 = c2.search(js5[pos:])
                assert s2 is not None, f"No end of comment found for comment starting with '{js5[pos:pos+50]}'"
                comments.update({pos + s2.start(): js5[pos : pos + s2.start()]})
                for p in range(pos, pos + s2.end()):
                    if js5[p] not in ("\r", "\n"):
                        _js5 += " "
                    else:
                        _js5 += js5[p]
                pos += s2.end()
        return _js5, comments

    def to_py(self) -> dict[str, Any]:
        """Translate json5 code 'self.js5' to a python dict and store as self.js_py."""
        self.pos = 0
        return self._object()

    def _strip(self, txt: str) -> str:
        """Strip white space from txt."""
        if txt == "":
            return txt
        len0 = len(txt)
        while True:
            txt = txt.strip()
            if len(txt) == len0:
                return txt
            else:
                len0 = len(txt)

    def _object(self) -> dict[str, Any]:
        """Start reading a json5 object { ... } at current position."""
        #        print(f"OBJECT({self.pos}): {self.js5[self.pos:]}")
        assert self.js5[self.pos] == "{", self._msg("object start '{' expected")
        self.pos += 1
        dct = None  # {}: dict[str,Any] = {}
        while True:
            r0, c0 = self._get_line_number(self.pos)
            k = self._key()  # read until ':'
            v = self._value()  # read until ',' or '}'
            # print(f"KEY:VALUE {k}:{v}. {r0}({c0}): '{self.js5[self.lines[r0-1]+c0 : self.lines[r0-1]+c0+50]+'...'}'")
            if k == "" and v == "" and self.js5[self.pos] == "}":
                self.pos += 1
                assert dct is not None, f"Cannot extract js5 object from {self.js5}"
                return dct
            else:
                assert k != "" and v != "", self._msg(f"No proper key:value: {k}:{v} within object.")
                assert dct is None or k not in dct, self._msg(
                    f"Duplicate key '{k}' within object starting at line {r0}({c0}). Not allowed."
                )
                if dct is None:
                    dct = {k: v}
                else:
                    dct.update({k: v})

    def _list(self) -> list:
        """Read and return a list object at the current position."""
        #        print(f"LIST({self.pos}): {self.js5[self.pos:]}")
        assert self.js5[self.pos] == "[", self._msg("List start '[' expected")
        self.pos += 1
        lst = []
        while True:
            v = self._value()
            #            print("LIST_VALUE", v, self.js5[self.pos])
            if v != "":
                lst.append(v)
            elif self.js5[self.pos] == "]":
                break
        assert self.js5[self.pos] == "]", self._msg("List end ']' expected")
        self.pos += 1
        return lst

    def _quoted(self, pos: int | None = None) -> tuple[int, int]:
        """Search for a string between quotes after pos ('...' or "...") with no other text before the first quote.

        Return the absolute position of the quote pair as tuple,
        such that self.js5[q1:q2] represents the quoted string with quotes, or (None,None).
        Note that the absolute position of the right quote is m2.start()=q2-1!
        """
        if pos is None:
            pos = self.pos
        m = re.search(r"'|\"", self.js5[pos:])
        if m is None or len(
            self.js5[pos : pos + m.start()].strip()
        ):  # non-white space before the quote is unacceptable
            return (-1, -1)
        m2 = re.search(m.group(), self.js5[pos + m.end() :])
        if m2 is None:
            return (-1, -1)
        return (pos + m.start(), pos + m.end() + m2.end())

    def _key(self) -> str:
        """Read and return a key at the current position, i.e. expect '<string>:'.

        Due to the fact that trailing ',' are allowed,
        we might find '}' or end of string, denoting an empty key/end of object.
        """
        q1, q2 = self._quoted()
        if q1 >= 0:  # found a quoted string
            self.pos = q2
            k = self.js5[q1 + 1 : q2 - 1]
            # print("QUOTED KEY", k, self.js5[self.pos :])
            m = re.search(r":", self.js5[self.pos :])
            assert m is not None, self._msg(f"Quoted key {k} found, but no ':'")
            assert not len(self.js5[self.pos : self.pos + m.start()].strip()), self._msg(
                f"Additional text '{self.js5[self.pos : self.pos+m.start()].strip()}' after key '{k}'"
            )
        else:
            m = re.search(r"[:\}]", self.js5[self.pos :])
            # print("KEY", self.pos, self.js5[self.pos : self.pos+50], m)
            assert m is not None, self._msg("key expected")
            if m.group() == "}":  # end of object, e.g. due to trailing ','
                return ""
            else:
                k = self.js5[self.pos : self.pos + m.start()]
        self.pos += m.end()
        return str(self._strip(k))

    def _value(self):
        """Read and return a value at the current position, i.e. expect ,'...', "...",}."""
        q1, q2 = self._quoted()
        if q2 < 0:  # no quotation found. Include also [ and { in search
            m = re.search(r"[\[,\{\}\]]", self.js5[self.pos :])
        else:  # quoted value. Should find , ] or } after the value
            self.pos = q2
            m = re.search(r"[,\}\]]", self.js5[self.pos :])
        #            print("Found quoted", self.js5[q1:q2], m)
        assert m is not None, self._msg("value expected")
        if m.group() in ("{", "["):  # found an object or a list start (quotation not allowed!)
            assert ":" not in self.js5[self.pos : self.pos + m.start()], self._msg("Found ':'. Forgot ','?")
            self.pos += m.start()
            v = self._object() if m.group() == "{" else self._list()
            m = re.search(r"[,\}\]]", self.js5[self.pos :])
            cr, cc = self._get_line_number(self.pos)
            assert m is not None, self._msg(f"End of value or end of object/list '{str(v)[:50]+'..'}' expected")
        elif m.group() in ("]", "}", ","):  # any allowed value separator (also last list/object value)
            v = self.js5[self.pos : self.pos + m.start()].strip() if q2 < 0 else self.js5[q1 + 1 : q2 - 1]
        else:
            raise Json5Error(
                f"Unhandled situation. Quoted: ({q1-self.pos},{q2-self.pos}), search: {m}. From pos: {self.js5[self.pos : ]}"
            )
        # save_pos = self.pos
        self.pos += (
            m.start() if m.group() in ("}", "]") else m.end()
        )  # leave the '}', ']', but make sure that ',' is eaten
        # print(f"VALUE. Jump:{self.js5[save_pos:self.pos]}, return:{v}")
        if isinstance(v, str):
            v = v.strip().strip("'").strip('"').strip()
            if q2 < 0:  # no quotation was used. Key separator not allowed.
                assert ":" not in v, self._msg(f"Key separator ':' in value: {v}. Forgot ','?")
        # print(f"VALUE {v} @ {self.pos}:'{self.js5[self.pos:self.pos+50]}'")
        if isinstance(v, (dict, list)):
            return v
        elif isinstance(v, str) and not len(v):  # might be empty due to trailing ','
            return ""

        try:
            return int(v)  # type: ignore
        except Exception:
            try:
                return float(v)  # type: ignore
            except Exception:
                if isinstance(v, str):
                    if v.upper() == "FALSE":
                        return False
                    if v.upper() == "TRUE":
                        return True
                    if v.upper() == "INFINITY":
                        return float("inf")
                    if v.upper() == "-INFINITY":
                        return float("-inf")
                    return str(v)
                else:
                    raise Json5Error(f"This should not happen. v:{v}") from None

    def jspath(self, path: str, typ: type | None = None, errorMsg: bool = False):
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
            path (str): path expression as string.
            typ (type)=None: optional specification of the expected type to find
            errMsg (bool)=False: specify whether an error should be raised, or None returned (default)
        """
        compiled = parse(path)
        data = compiled.find(self.js_py)
        #        print("DATA", data)
        val = None
        msg = ""
        if not len(data):  # not found
            msg = f"No match for {path}"
        elif len(data) == 1:  # found a single element
            val = data[0].value
        else:  # multiple elements
            if isinstance(data[0], DatumInContext):
                val = [x.value for x in data]

        if val is not None and typ is not None:  # check also the type
            if not isinstance(val, typ):
                try:  # try to convert
                    val = typ(val)
                except Exception:
                    msg = f"{path} matches, but type {typ} does not match {type(val)}."
                    val = None
        if val is None and errorMsg:
            raise ValueError(msg)
        return val

    @staticmethod
    def _spath_to_keys(spath):
        """Extract the keys from path.
        So far this is a minimum implementation for adding data. Probably this could be done using jysonpath-ng.
        """
        keys = []
        spath = spath.lstrip("$.")
        if spath.startswith("$["):
            spath = spath[1:]
        c = re.compile(r"\[(.*?)\]")
        while True:
            m = c.search(spath)
            if m is not None:
                if m.start() > 0:
                    keys.extend(spath[: m.start()].split("."))
                keys.append(spath[m.start() + 1 : m.end() - 1])
                spath = spath[m.end() :]
            elif not len(spath.strip()):
                break
            else:
                keys.extend(spath.split("."))
                break
        return keys

    @staticmethod
    def check_valid_js(js_py, print_msg=False):
        """Check whether the dict js_py is a valid Json dict."""

        def check_valid_js_list(lst):
            for itm in lst:
                if isinstance(itm, dict):
                    return Json5.check_valid_js(itm, print_msg=False)
                elif isinstance(itm, list):
                    return check_valid_js_list(itm)
                else:  # accept as Json atom
                    pass
            return True

        if not isinstance(js_py, dict):
            if print_msg:
                print(f"Error Not a (sub-)dict. Found type {type(js_py)}: {js_py}")
            return False
        for k, v in js_py.items():
            if not isinstance(k, str):
                if print_msg:
                    print(f"Error: Key {k} is not a string. (sub-)dict:{js_py}")
                return False
            if isinstance(v, dict):  # a sub-Json dict
                if not Json5.check_valid_js(v, print_msg):
                    if print_msg:
                        print(f"Error: Not a valid Json dict: {v}")
            elif isinstance(v, list):
                if not check_valid_js_list(v):
                    if print_msg:
                        print(f"Error: Not a valid Json list: {v}")
                    return False
            else:  # accept as atom
                pass
        return True

    def update(self, spath: str, data: Any):
        """Append data to the js_py dict at the path pointed to by keys.
        So far this is a minimum implementation for adding data. Probably this could be done using jysonpath-ng.
        """

        keys = Json5._spath_to_keys(spath)
        path = self.js_py
        parent = path
        for i, k in enumerate(keys):
            if k not in path:
                for j in range(len(keys) - 1, i - 1, -1):
                    data = {keys[j]: data}
                break
            else:
                parent = path
                path = path[k]  # type: ignore [assignment]
        # print(f"UPDATE path:{path}, parent:{parent}, k:{k}: {data}")
        if isinstance(path, list):
            path.append(data)
        elif isinstance(path, dict):
            path.update(data)
        elif isinstance(parent, dict):  # update the parent dict (replace a value)
            parent.update({k: data})
        else:
            raise ValueError(f"Unknown type of path: {path}")

    def write(self, file: str | os.PathLike[str] | None = None, pretty_print: bool = True):
        """Write a Json(5) tree to string or file.

        Args:
            file (str, Path)=None: The file name (as string or Path object) or None. If None, a string is returned.
            pretty_print (bool)=True: Denote whether the string/file should be pretty printed (LF,indents).

        Returns: The serialized Json(5) object as string. This string is optionally written to file.
        """

        def remove_comma(txt: str) -> str:
            for i in range(len(txt) - 1, -1, -1):
                if txt[i] == ",":
                    return txt[:i]
            return ""

        def print_js5(sub: Any, level: int = 0, pretty: bool = True) -> str:
            """Print the Json5 object recursively. Return the formated string.

            Args:
                sub (dict): the Json5 object to print
                level (int)=0: level in recursive printing. Used for indentation.
                pretty (bool)=True: Pretty print (LF and indentation).
            """
            if isinstance(sub, dict):
                res = "{"
                for k, v in sub.items():  # print the keys and values of dicts
                    res += "\n" + "   " * level if pretty else ""
                    res += "   " * level if pretty else ""
                    res += str(k)
                    res += " : " if pretty else ":"
                    res += print_js5(v, level + 1, pretty)
                res += "\n" + "   " * level if pretty else ""
                res = remove_comma(res)
                res += "}," if level > 0 else "}"
                res += "\n" if pretty else ""
            elif isinstance(sub, list):
                res = "["
                for v in sub:
                    sub_res = print_js5(v, level=level, pretty=pretty)
                    res += "" if sub_res is None else sub_res
                res = remove_comma(res)
                res += "],"
                res += "\n" if pretty else ""
            elif sub == "":
                res = ","
            elif isinstance(sub, str):
                res = "'" + str(sub) + "',"
            elif isinstance(sub, (int, float, bool)):
                res = str(sub) + ","
            else:  # try still to make a string
                res = str(sub) + ","
            return res

        js5 = print_js5(self.js_py, level=0, pretty=pretty_print)
        if file:
            with open(file, "w") as fp:
                fp.write(js5)
        return js5
