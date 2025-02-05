import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile


def match_with_wildcard(findtxt: str, matchtxt: str) -> bool:
    """Check whether 'findtxt' matches 'matchtxt'.

    Args:
        findtxt (str): the text string which is checked. It can contain wildcard characters '*', matching zero or more of any character.
        matchtxt (str): the text agains findtxt is checked
    Returns: True/False
    """
    if "*" not in findtxt:  # no wildcard characters
        return matchtxt == findtxt
    # there are wildcards
    m = re.search(pattern=findtxt.replace("*", ".*"), string=matchtxt)
    return m is not None


def from_xml(file: Path, sub: str | None = None) -> ET.Element:
    """Retrieve the Element root from a zipped file (retrieve sub), or an xml file (sub unused).
    If xpath is provided only the xpath matching element (using findall) is returned.
    """
    if is_zipfile(file) and sub is not None:  # expect a zipped archive containing xml file 'sub'
        with ZipFile(file) as zp:
            try:
                xml = zp.read(name=sub).decode(encoding="utf-8")
            except BadZipFile as e:
                raise RuntimeError(f"File '{sub}' not found in {file}.") from e
    elif not is_zipfile(file) and file.exists() and sub is None:  # expect an xml file
        with file.open(encoding="utf-8") as f:
            xml = f.read()
    else:
        raise RuntimeError(f"It was not possible to read an XML from file {file}, sub {sub}")

    try:
        et = ET.fromstring(text=xml)  # noqa: S314
    except ET.ParseError as e:
        raise RuntimeError(f"File '{file}' does not seem to be a proper xml file") from e

    return et
