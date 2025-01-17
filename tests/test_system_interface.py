from enum import Enum
from pathlib import Path

import pytest

from sim_explorer.system_interface import SystemInterface


def test_read_system_structure():
    for file in ("crane_table.js5", "crane_table.xml"):
        s = SystemInterface.read_system_structure(Path(__file__).parent / "data" / "MobileCrane" / file)
        # print(file, s)
        assert s["header"]["version"] == "0.1", f"Found {s['header']['version']}"
        assert s["header"]["xmlns"] == "http://opensimulationplatform.com/MSMI/OSPSystemStructure"
        assert s["header"]["StartTime"] == 0.0
        assert s["header"]["Algorithm"] == "fixedStep"
        assert s["header"]["BaseStepSize"] == 0.01
        assert len(s["Simulators"]) == 2
        assert (
            s["Simulators"]["simpleTable"]["source"]
            == Path(__file__).parent / "data" / "SimpleTable" / "SimpleTable.fmu"
        )
        assert s["Simulators"]["mobileCrane"]["pedestal.pedestalMass"] == 5000.0


def test_pytype():
    assert SystemInterface.pytype("Real") is float
    assert SystemInterface.pytype("Enumeration") is Enum
    assert SystemInterface.pytype("Real", 1) == 1.0
    assert SystemInterface.pytype("Integer", 1) == 1
    assert SystemInterface.pytype("String", 1.0) == "1.0"


def test_interface():
    sys = SystemInterface(Path(__file__).parent / "data" / "MobileCrane" / "crane_table.js5")
    # manually adding another SimpleTable to the system
    sys._models["SimpleTable"]["components"].append("simpleTable2")
    sys.components.update({"simpleTable2": "SimpleTable"})
    assert isinstance(sys, SystemInterface)
    assert list(sys.components.keys()) == ["simpleTable", "mobileCrane", "simpleTable2"]
    assert len(sys.models) == 2
    assert tuple(sys.models.keys()) == ("SimpleTable", "MobileCrane"), f"Found:{sys.models}"
    m = sys.match_components("simple*")
    assert m[0] == "SimpleTable", f"Found {m[0]}"
    assert m[1] == ("simpleTable", "simpleTable2")
    for k in sys.components.keys():
        assert sys.component_name_from_id(sys.component_id_from_name(k)) == k
    vars = sys.variables("simpleTable")
    assert vars["interpolate"]["causality"] == "parameter"
    assert vars["interpolate"]["type"] is bool, f"Found {vars['interpolate']['type']}"
    assert sys.match_variables("simpleTable", "outs") == (("outs[0]", 0), ("outs[1]", 1), ("outs[2]", 2))
    assert sys.match_variables("simpleTable", "interpolate") == (("interpolate", 3),)
    assert sys.variable_name_from_ref("simpleTable", 2) == "outs[2]"
    assert sys.variable_name_from_ref("simpleTable", 100) == "", "Not existent"
    default = SystemInterface.default_initial("output", "fixed")
    assert default == -5, f"Found:{default}"
    assert SystemInterface.default_initial("parameter", "fixed") == "exact"
    assert sys.allowed_action("Set", "simpleTable", "interpolate", 0)
    assert sys.allowed_action("Get", "simpleTable", "outs", 0)
    # assert sys.message, "Variable outs of component simpleTable was not found"

    with pytest.raises(NotImplementedError) as err:
        sys.do_action(0.0, (0, 1), float)
    assert str(err.value) == "The method 'do_action()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.action_step((0, 1), float)
    assert str(err.value) == "The method 'action_step()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.init_simulator()
    assert str(err.value) == "The method 'init_simulator()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.run_until(9.9)
    assert str(err.value) == "The method 'run_until()' cannot be used in SystemInterface"


def test_update_refs_values():
    refs, vals = SystemInterface.update_refs_values((1, 3, 5, 7), (1, 5), (1.0, 5.0), (3, 5), (3.1, 5.1))
    assert refs == (1, 3, 5)
    assert vals == (1.0, 3.1, 5.1)
    with pytest.raises(ValueError) as err:
        refs, vals = SystemInterface.update_refs_values((1, 3, 5, 7), (1, 5), (1.0, 5.0), (3, 6), (3.1, 5.1))
    assert str(err.value) == "tuple.index(x): x not in tuple"
    refs, vals = SystemInterface.update_refs_values((1, 3, 5, 7), (1, 3), (1.0, 3.0), (5, 7), (5.1, 7.1))
    assert refs == (1, 3, 5, 7)
    assert vals == (1.0, 3.0, 5.1, 7.1)


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_read_system_structure()
    # test_pytype()
    # test_interface()
    # test_update_refs_values()
