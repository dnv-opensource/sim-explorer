import time
from pathlib import Path

import pytest
from sim_explorer.json5 import Json5


@pytest.fixture(scope="session")
def ex(scope="session"):
    return _rfc9535_example()


def _rfc9535_example():
    js5 = """{ store: {
    book: [
      { category: "reference",
        author: "Nigel Rees",
        title: "Sayings of the Century",
        price: 8.95
      },
      { category: "fiction",
        author: "Evelyn Waugh",
        title: "Sword of Honour",
        price: 12.99
      },
      { category: "fiction",
        author: "Herman Melville",
        title: "Moby Dick",
        isbn: "0-553-21311-3",
        price: 8.99
      },
      { category: "fiction",
        author: "J. R. R. Tolkien",
        title: "The Lord of the Rings",
        isbn: "0-395-19395-8",
        price: 22.99
      }
    ],
    bicycle: {
      color: "red",
      price: 399
    }
    }}"""
    js = Json5(js5)
    return js


def test_jpath(ex):
    assert isinstance(ex.js_py, dict), f"Expect dict. Found {ex.js_py}"
    print(f"DICT {ex.js_py}")
    found = ex.jspath("$.store.book[*].author", list)
    assert found == [
        "Nigel Rees",
        "Evelyn Waugh",
        "Herman Melville",
        "J. R. R. Tolkien",
    ], f"The authors of all books in the store: {found}"
    found = ex.jspath("$..author", list)
    assert found == ["Nigel Rees", "Evelyn Waugh", "Herman Melville", "J. R. R. Tolkien"], f"All authors: {found}"
    found = ex.jspath("$.store.*", list)
    assert isinstance(found[0], list) and isinstance(found[1], dict), "Everything ins store: books and a bike"
    assert ex.jspath("$.store..price", list) == [8.95, 12.99, 8.99, 22.99, 399], "Price of all articles in the store"
    found = ex.jspath("$..book[2]", typ=dict)
    expected = {
        "category": "fiction",
        "author": "Herman Melville",
        "title": "Moby Dick",
        "isbn": "0-553-21311-3",
        "price": 8.99,
    }
    assert found == expected, "The third book"
    assert ex.jspath("$..book[2].author", str) == "Herman Melville", "The third book's author"
    found = ex.jspath("$..book[2].publisher", str)
    assert found is None, f"Result not empty (the third book does not have a 'publisher' member): {found}"
    found = ex.jspath("$..book[-1]", dict)
    expected = {
        "category": "fiction",
        "author": "J. R. R. Tolkien",
        "title": "The Lord of the Rings",
        "isbn": "0-395-19395-8",
        "price": 22.99,
    }
    assert found == expected, f"The last book in order: {found}"
    found = ex.jspath("$..book[:2]", list)
    assert len(found) == 2, f"The first two books: {found}"
    # found = ex.jspath( '$..book[0,1]', list) #!! does not seem to work, but [:2] works
    # assert len(found)==2, f"The first two books: {found}"
    assert 2 == len(ex.jspath("$..book[?@.isbn]", list)), "All books with an ISBN number"
    assert 2 == len(ex.jspath("$..book[?@.price<10]", None)), "All books cheaper than 10"
    assert 23 == len(ex.jspath("$..*", list)), "All member values and array elements contained in the input value"
    # working with expected match and expected type, raising an error message, or not
    assert ex.jspath("$..book[2].authors", typ=str, errorMsg=False) is None, "Fail silently"
    with pytest.raises(ValueError) as err:
        found = ex.jspath("$..book[2].authors", typ=str, errorMsg=True)
    assert str(err.value) == "No match for $..book[2].authors", f"ERR:{err.value}"

    assert ex.jspath("$..book[2].author", typ=float, errorMsg=False) is None, "Fail silently"
    with pytest.raises(ValueError) as err:
        found = ex.jspath("$..book[2].author", typ=float, errorMsg=True)
    assert (
        str(err.value) == "$..book[2].author matches, but type <class 'float'> does not match <class 'str'>."
    ), f"ERR:{err.value}"

    # some selected jsonpath extensions:
    # not yet tested (not found out how it is done):
    # where: jsonpath1 where jsonpath2 : Any nodes matching jsonpath1 with a child matching jsonpath2
    # wherenot: jsonpath1 wherenot jsonpath2 : Any nodes matching jsonpath1 with a child not matching jsonpath2
    # |: works but strange result: found = ex.jspath( '$..book[?@.price<10] | $..book[?@.price>10]', None)

    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, 0.0 : { bb: { h : [0,0,1], v : 2.3}}}")
    assert js.jspath("$['0.0']", dict) == {"bb": {"h": [0, 0, 1], "v": 2.3}}, "Use [] notation when path includes '.'"
    # print("FOUND", type(found), 0 if found is None else len(found), found)

    # run directly on dict:
    js_py = {"header": {"case": "Test", "timeFactor": 1.0}, "0.0": {"bb": {"h": [0, 0, 1], "v": 2.3}}}
    assert Json5(js_py).jspath("$['0.0']") == {"bb": {"h": [0, 0, 1], "v": 2.3}}


def test_update(ex):
    assert Json5._spath_to_keys("$.Hei[ho]Hi[ha]he.hu") == ["Hei", "ho", "Hi", "ha", "he", "hu"]
    assert Json5._spath_to_keys("$.Hei[0.0]Hi[1.0]he.hu") == ["Hei", "0.0", "Hi", "1.0", "he", "hu"]

    # ex.js_py['store']['book'].append({'category':'crime','author':'noname'})
    # print(ex.js_py)
    # print("FOUND", type(found), 0 if found is None else len(found), found)

    ex.update("$.store.book", {"category": "crime", "author": "noname"})
    assert ex.jspath("$..book[-1]", typ=dict) == {"category": "crime", "author": "noname"}, "Book added"

    # start with header and add the first data
    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, ")
    js.update("$[0.0]bb", {"f": 9.9})
    expected = {"header": {"case": "Test", "timeFactor": 1.0}, "0.0": {"bb": {"f": 9.9}}}
    assert js.js_py == expected

    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, 0.0 : { bb: { h : [0,0,1], v : 2.3}}}")
    js.update("$[0.0]bb", {"f": 9.9})
    expected = {"header": {"case": "Test", "timeFactor": 1.0}, "0.0": {"bb": {"h": [0, 0, 1], "v": 2.3, "f": 9.9}}}
    assert js.js_py == expected

    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, 0.0 : { bb: { h : [0,0,1], v : 2.3}}}")
    js.update("$[0.0]", {"bc": {"f": 9.9}})
    expected = {
        "header": {"case": "Test", "timeFactor": 1.0},
        "0.0": {"bb": {"h": [0, 0, 1], "v": 2.3}, "bc": {"f": 9.9}},
    }
    assert js.js_py == expected, f"\n{js.js_py}\n !=\n{expected}"

    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, 0.0 : { bb: { h : [0,0,1], v : 2.3}}}")
    js.update("$.", {"1.0": {"bb": {"h": [0, 0, 0.98]}}})
    expected = {
        "header": {"case": "Test", "timeFactor": 1.0},
        "0.0": {"bb": {"h": [0, 0, 1], "v": 2.3}},
        "1.0": {"bb": {"h": [0, 0, 0.98]}},
    }
    assert js.js_py == expected

    js = Json5("{header : { case : 'Test', timeFactor : 1.0}, 0.0 : { bb: { h : [0,0,1], v : 2.3}}}")
    js.update("$.header.case", "Operation")
    assert js.jspath("$.header.case") == "Operation", "Changed a dict value"


def test_json5_syntax():
    assert Json5("Hello World", False).js5 == "{ Hello World }", "Automatic addition of '{}' did not work"
    js = Json5("Hello\nWorld\rHei\n\rHo\r\nHi", auto=False)
    assert js.lines[6] == 24, f"Line 6 should start at {js.lines[6]}"
    assert js.js5 == "{ Hello World Hei Ho Hi }", "Automatic replacement of newlines did not work"
    assert js.line(-1)[-1] == "}", "Ending '}' expected"
    assert js.line(3) == "Hei", "Quote of line 3 wrong"
    assert js.line(5) == "Hi", "Quote of line 5 wrong"
    js = Json5("Hello 'W\norld'", 0).js5
    assert Json5("Hello 'W\norld'", 0).js5[10] == "\n", "newline within quotations should not be replaced"
    assert Json5("He'llo 'Wo'rld'", 0).js5 == "{ He'llo 'Wo'rld' }", "Handling of single quotes not correct"
    assert (
        len(Json5("Hello World //added a EOL comment", 0).js5) == len("Hello World //added a EOL comment") + 4
    ), "Length of string not conserved when replacing comment"

    assert Json5("Hello//EOL comment", 0).js5 == "{ Hello              }", "Comment not properly replaced"
    assert Json5("Hello#EOL comment", 0).js5 == "{ Hello             }", "Comment not properly replaced"
    raw = """{spec: {
           dp:1.5, #'com1'
           dr@0.9 : 10,  # "com2"
           }}"""
    js = Json5(raw)
    assert js.comments == {28: "#'com1'", 61: '# "com2"'}, "Comments not extracted as expected"
    assert js.js_py["spec"]["dp"] == 1.5, "Comments not properly removed"
    js = Json5("Hello /*Line1\nLine2\n..*/..", 0)
    assert js.js5 == "{ Hello                   .. }", "Incorrect multi-line comment"
    assert Json5("{'Hi':1, Ho:2}").js_py == {"Hi": 1.0, "Ho": 2.0}, "Simple dict expected. Second key without '"
    assert Json5("{'Hello:@#%&/=?World':1}").to_py() == {
        "Hello:@#%&/=?World": 1
    }, "Literal string keys should handle any character, including':' and comments"

    js = Json5("{Start: {\n   'H':1,\n   99:{'e':11,'l':12}},\nLast:999}")
    assert js.to_py() == {"Start": {"H": 1, "99": {"e": 11, "l": 12}}, "Last": 999}, "Dict of dict dict expected"

    assert Json5("{'H':1, 99:['e','l','l','o']}").js_py == {
        "H": 1,
        "99": ["e", "l", "l", "o"],
    }, "List as value expected"

    js = Json5("{'H':1, 99:['e','l','l','o'], 'W':999}")
    assert list(js.js_py.keys()) == ["H", "99", "W"], "Additional or missing main object elements"
    with pytest.raises(AssertionError) as err:
        Json5("{ H : 1,2}")
    assert str(err.value).startswith("Json5 read error at 1(10): No proper key:value:")
    js = Json5(
        "{   spec: {\n     stopTime : '3',\n      bb.h : '10.0',\n      bb.v : '[0.0, 1.0, 3.0]',\n      bb.e : '0.7',\n   }}"
    )
    #        print(js.js5)
    with pytest.raises(AssertionError) as err:
        js = Json5(
            "{   spec: {\n     stopTime : 3\n    bb.h : '10.0',\n      bb.v : '[0.0, 1.0, 3.0]',\n      bb.e : '0.7',\n   }}"
        )
    assert str(err.value).startswith("Json5 read error at 3(19): Key separator ':' in value")

    with pytest.raises(AssertionError) as err:
        js = Json5("{spec: {\n da_dt : [0,0,0,0], dp_dt : 0 db_dt : 0  v     : [0,0,0,0],}}")
    assert str(err.value).startswith("Json5 read error at 2(28): Found ':'")


def test_write():
    js1 = {"key1": 1.0, "key2": "a string", "key3": ["a", "list", "including", "numbers", 9.9, 1]}
    expected = "{key1:1.0,key2:'a string',key3:['a','list','including','numbers',9.9,1]}"
    js = Json5(str(js1))
    assert js.write(pretty_print=False) == expected, "Simple JSON5 dict"

    js2 = {
        "key1": 1.0,
        "key2": "a string",
        "key3": [
            "a",
            "list",
            "including",
            "numbers",
            9.9,
            1,
            "+ object",
            {"hello": 1, "World": 2, "dict": {"hi": 2.1, "ho": 2.2}},
        ],
    }
    expected = "{key1:1.0,key2:'a string',key3:['a','list','including','numbers',9.9,1,'+ object',{hello:1,World:2,dict:{hi:2.1,ho:2.2}}]}"
    js = Json5(str(js2))
    assert js.write(pretty_print=False) == expected, "Json5 with object within list"

    txt = js.write(pretty_print=True)
    assert len(txt) == 189, "Length of pretty-printed JSON5"
    print(txt)


def test_results_header():
    js_txt = (
        """{Header : {
                 case : 'base',
                 dateTime : '"""
        + time.asctime(time.localtime(12345))
        + """',
                 cases : 'BouncingBall',
                 file : '"""
        + Path(__file__).as_posix()
        + """',
                 casesDate : '"""
        + time.asctime(time.localtime(123456))
        + """',
                 timeUnit : 'second',
                 timeFactor : 1000000000.0}, }"""
    )
    # print(js_txt)
    header = Json5(js_txt).js_py
    assert header["Header"]["case"] == "base"
    # Commented out as this dateTime is different on different operating systems
    # assert header["Header"]["dateTime"] == "Thu Jan  1 04:25:45 1970"


def test_read_cases():
    bb_cases = Path(__file__).parent.joinpath("data/BouncingBall0/BouncingBall.cases")
    js = Json5(bb_cases)
    assert Json5.check_valid_js(js.js_py, print_msg=True)
    assert js.jspath("$.header.name") == "BouncingBall"


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_json5_syntax()
    # test_results_header()
    # rfc = _rfc9535_example()
    # test_jpath(rfc)
    # test_update(rfc)
    # test_results_header()
    # test_write()
    # test_read_cases()
