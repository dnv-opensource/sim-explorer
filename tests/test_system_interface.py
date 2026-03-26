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
            s["Simulators"]["timeTable"]["source"] == Path(__file__).parent / "data" / "TimeTable" / "TimeTableFMU.fmu"
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
    # manually adding another TimeTable to the system
    sys._models["TimeTableFMU"]["components"].append("timeTable2")  # pyright: ignore[reportPrivateUsage]
    sys.components.update({"timeTable2": "TimeTableFMU"})
    assert isinstance(sys, SystemInterface)
    assert list(sys.components.keys()) == ["timeTable", "mobileCrane", "timeTable2"]
    assert len(sys.models) == 2
    assert tuple(sys.models.keys()) == ("TimeTableFMU", "MobileCrane"), f"Found:{sys.models}"
    m = sys.match_components("time*")
    assert m[0] == "TimeTableFMU", f"Found {m[0]}"
    assert m[1] == ("timeTable", "timeTable2")
    for k in sys.components:
        assert sys.component_name_from_id(sys.component_id_from_name(k)) == k
    variables = sys.variables("timeTable")
    assert variables["interpolate"]["causality"] == "parameter"
    assert variables["interpolate"]["type"] is int, f"Found {variables['interpolate']['type']}"
    assert sys.match_variables("timeTable", "outs") == (("outs[0]", 1), ("outs[1]", 2), ("outs[2]", 3))
    assert sys.match_variables("timeTable", "interpolate") == (("interpolate", 0),)
    assert sys.variable_name_from_ref("timeTable", 2) == "outs[1]"
    assert sys.variable_name_from_ref("timeTable", 100) == "", "Not existent"
    default = SystemInterface.valid_initial("output", "fixed")[0]
    assert default.startswith("ERROR"), f"Found:{default}"
    assert SystemInterface.valid_initial("parameter", "fixed")[0] == "exact"
    assert sys.allowed_action("Set", "timeTable", "interpolate", 0)
    assert sys.allowed_action("Get", "timeTable", "outs", 0)
    # assert sys.message, "Variable outs of component timeTable was not found"

    with pytest.raises(NotImplementedError) as err:
        _ = sys.do_action(time=0.0, act_info=(0, 1), typ=float)  # type: ignore[arg-type]
    assert str(err.value) == "The method 'do_action()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.action_step(act_info=(0, 1), typ=float)  # type: ignore[arg-type]
    assert str(err.value) == "The method 'action_step()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.init_simulator()
    assert str(err.value) == "The method 'init_simulator()' cannot be used in SystemInterface"
    with pytest.raises(NotImplementedError) as err:
        _ = sys.run_until(time=9.9)
    assert str(err.value) == "The method 'run_until()' cannot be used in SystemInterface"


def test_update_refs_values():
    refs, vals = SystemInterface.update_refs_values(
        allrefs=(1, 3, 5, 7),
        baserefs=(1, 5),
        basevals=(1.0, 5.0),
        refs=(3, 5),
        values=(3.1, 5.1),
    )
    assert refs == (1, 3, 5)
    assert vals == (1.0, 3.1, 5.1)
    with pytest.raises(ValueError) as err:
        refs, vals = SystemInterface.update_refs_values(
            allrefs=(1, 3, 5, 7),
            baserefs=(1, 5),
            basevals=(1.0, 5.0),
            refs=(3, 6),
            values=(3.1, 5.1),
        )
    assert str(err.value) == "tuple.index(x): x not in tuple"
    refs, vals = SystemInterface.update_refs_values(
        allrefs=(1, 3, 5, 7),
        baserefs=(1, 3),
        basevals=(1.0, 3.0),
        refs=(5, 7),
        values=(5.1, 7.1),
    )
    assert refs == (1, 3, 5, 7)
    assert vals == (1.0, 3.0, 5.1, 7.1)


if __name__ == "__main__":
    retcode = pytest.main(["-rA", "-v", __file__])
    assert retcode == 0, f"Non-zero return code {retcode}"
    # test_read_system_structure()
    # test_pytype()
    # test_interface()
    # test_update_refs_values()
