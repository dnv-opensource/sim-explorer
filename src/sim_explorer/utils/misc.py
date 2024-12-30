import re
import xml.etree.ElementTree as ET  # noqa: N817
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
    else:  # there are wildcards
        m = re.search(findtxt.replace("*", ".*"), matchtxt)
        return m is not None


def from_xml(file: Path, sub: str | None = None) -> ET.Element:
    """Retrieve the Element root from a zipped file (retrieve sub), or an xml file (sub unused).
    If xpath is provided only the xpath matching element (using findall) is returned.
    """
    if is_zipfile(file) and sub is not None:  # expect a zipped archive containing xml file 'sub'
        with ZipFile(file) as zp:
            try:
                xml = zp.read(sub).decode("utf-8")
            except BadZipFile as err:
                raise Exception(f"File '{sub}' not found in {file}: {err}") from err
    elif not is_zipfile(file) and file.exists() and sub is None:  # expect an xml file
        with open(file, encoding="utf-8") as f:
            xml = f.read()
    else:
        raise Exception(f"It was not possible to read an XML from file {file}, sub {sub}") from None

    try:
        et = ET.fromstring(xml)
    except ET.ParseError as err:
        raise Exception(f"File '{file}' does not seem to be a proper xml file") from err

    return et
