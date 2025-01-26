import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from component_model.utils.xml import read_xml

from sim_explorer.json5 import Json5


# ==========================================
# Open Simulation Platform related functions
# ==========================================
def make_osp_system_structure(
    name: str = "OspSystemStructure",
    version: str = "0.1",
    start: float = 0.0,
    base_step: float = 0.01,
    algorithm: str = "fixedStep",
    simulators: dict | None = None,
    functions_linear: dict | None = None,
    functions_sum: dict | None = None,
    functions_vectorsum: dict | None = None,
    connections_variable: tuple = (),
    connections_signal: tuple = (),
    connections_group: tuple = (),
    connections_signalgroup: tuple = (),
    path: Path | str = ".",
):
    """Prepare a OspSystemStructure xml file according to `OSP configuration specification <https://open-simulation-platform.github.io/libcosim/configuration>`_.

    Args:
        name (str)='OspSystemStructure': the name of the system model, used also as file name
        version (str)='0.1': The version of the OspSystemConfiguration xmlns
        start (float)=0.0: The simulation start time
        base_step (float)=0.01: The base stepSize of the simulation. The exact usage depends on the algorithm chosen
        algorithm (str)='fixedStep': The name of the algorithm
        simulators (dict)={}: dict of models (in OSP called 'simulators'). Per simulator:
           <instance> : {source: , stepSize: , <var-name>: value, ...} (values as python types)
        functions_linear (dict)={}: dict of LinearTransformation function. Per function:
           <name> : {factor: , offset: }
        functions_sum (dict)={}: dict of Sum functions. Per function:
           <name> : {inputCount: } (number of inputs to sum over)
        functions_vectorsum (dict)={}: dict of VectorSum functions. Per function:
           <name> : {inputCount: , numericType: , dimension: }
        connections_variable (tuple)=(): tuple of model connections.
           Each connection is defined through (model, out-variable, model, in-variable)
        connections_signal (tuple)=(): tuple of signal connections:
           Each connection is defined through (model, variable, function, signal)
        connections_group (tuple)=(): tuple of group connections:
           Each connection is defined through (model, group, model, group)
        connections_signalgroup (tuple)=(): tuple of signal group connections:
           Each connection is defined through (model, group, function, signal-group)
        dest (Path,str)='.': the path where the file should be saved

    Returns
    -------
        The absolute path of the file as Path object

        .. todo:: better stepSize control in dependence on algorithm selected, e.g. with fixedStep we should probably set all step sizes to the minimum of everything?
    """

    def element_text(tag: str, attr: dict | None = None, text: str | None = None):
        el = ET.Element(tag, {} if attr is None else attr)
        if text is not None:
            el.text = text
        return el

    def make_simulators(simulators: dict | None):
        """Make the <simulators> element (list of component models)."""

        def make_initial_value(var: str, val: bool | int | float | str):
            """Make a <InitialValue> element from the provided var dict."""
            typ = {bool: "Boolean", int: "Integer", float: "Real", str: "String"}[type(val)]
            initial = ET.Element("InitialValue", {"variable": var})
            ET.SubElement(initial, typ, {"value": ("false", "true")[int(val)] if isinstance(val, bool) else str(val)})
            return initial

        _simulators = ET.Element("Simulators")
        if simulators is not None:
            for m, props in simulators.items():
                simulator = ET.Element(
                    "Simulator",
                    {
                        "name": m,
                        "source": props.get("source", m[0].upper() + m[1:] + ".fmu"),
                        "stepSize": str(props.get("stepSize", base_step)),
                    },
                )
                initial = ET.Element("InitialValues")
                for var, value in props.items():
                    if var not in ("source", "stepSize"):
                        initial.append(make_initial_value(var, value))
                if len(initial):
                    simulator.append(initial)
                _simulators.append(simulator)
            #            print(f"Model {m}: {simulator}. Length {len(simulators)}")
            #            ET.ElementTree(simulators).write("Test.xml")
        return _simulators

    def make_functions(f_linear: dict | None, f_sum: dict | None, f_vectorsum: dict | None):
        _functions = ET.Element("Functions")
        if f_linear is not None:
            for key, val in f_linear:
                _functions.append(
                    ET.Element("LinearTransformation", {"name": key, "factor": val["factor"], "offset": val["offset"]})
                )
        if f_sum is not None:
            for key, val in f_sum:
                _functions.append(ET.Element("Sum", {"name": key, "inputCount": val["inputCount"]}))
        if f_vectorsum is not None:
            for key, val in f_vectorsum:
                _functions.append(
                    ET.Element(
                        "VectorSum",
                        {
                            "name": key,
                            "inputCount": val["inputCount"],
                            "numericType": val["numericType"],
                            "dimension": val["dimension"],
                        },
                    )
                )
        return _functions

    def make_connections(c_variable: tuple, c_signal: tuple, c_group: tuple, c_signalgroup: tuple):
        """Make the <connections> element from the provided con."""

        def make_connection(main: str, sub1: str, attr1: dict, sub2: str, attr2: dict):
            el = ET.Element(main)
            ET.SubElement(el, sub1, attr1)
            ET.SubElement(el, sub2, attr2)
            return el

        _cons = ET.Element("Connections")
        for m1, v1, m2, v2 in c_variable:
            _cons.append(
                make_connection(
                    "VariableConnection",
                    "Variable",
                    {"simulator": m1, "name": v1},
                    "Variable",
                    {"simulator": m2, "name": v2},
                )
            )
        for m1, v1, f, v2 in c_signal:
            _cons.append(
                make_connection(
                    "SignalConnection", "Variable", {"simulator": m1, "name": v1}, "Signal", {"function": f, "name": v2}
                )
            )
        for m1, g1, m2, g2 in c_group:
            _cons.append(
                make_connection(
                    "VariableGroupConnection",
                    "VariableGroup",
                    {"simulator": m1, "name": g1},
                    "VariableGroup",
                    {"simulator": m2, "name": g2},
                )
            )
        for m1, g1, f, g2 in c_signalgroup:
            _cons.append(
                make_connection(
                    "SignalGroupConnection",
                    "VariableGroup",
                    {"simulator": m1, "name": g1},
                    "SignalGroup",
                    {"function": f, "name": g2},
                )
            )
        return _cons

    osp = ET.Element(
        "OspSystemStructure", {"xmlns": "http://opensimulationplatform.com/MSMI/OSPSystemStructure", "version": version}
    )
    osp.append(element_text("StartTime", text=str(start)))
    osp.append(element_text("BaseStepSize", text=str(base_step)))
    osp.append(make_simulators(simulators))
    osp.append(make_functions(functions_linear, functions_sum, functions_vectorsum))
    osp.append(make_connections(connections_variable, connections_signal, connections_group, connections_signalgroup))
    tree = ET.ElementTree(osp)
    ET.indent(tree, space="   ", level=0)
    file = Path(path).absolute() / f"{name}.xml"
    tree.write(file, encoding="utf-8")
    return file


def osp_system_structure_from_js5(file: Path, dest: Path | None = None):
    """Make a OspSystemStructure file from a js5 specification.
    The js5 specification is closely related to the make_osp_systemStructure() function (and uses it).
    """
    assert file.exists(), f"File {file} not found"
    assert file.name.endswith(".js5"), f"Json5 file expected. Found {file.name}"
    js = Json5(file)

    ss = make_osp_system_structure(
        name=file.name[:-4],
        version=js.jspath("$.header.version", str) or "0.1",
        start=js.jspath("$.header.StartTime", float) or 0.0,
        base_step=js.jspath("$.header.BaseStepSize", float) or 0.01,
        algorithm=js.jspath("$.header.algorithm", str) or "fixedStep",
        simulators=js.jspath("$.Simulators", dict) or {},
        functions_linear=js.jspath("$.FunctionsLinear", dict) or {},
        functions_sum=js.jspath("$.FunctionsSum", dict) or {},
        functions_vectorsum=js.jspath("$.FunctionsVectorSum", dict) or {},
        connections_variable=tuple(js.jspath("$.ConnectionsVariable", list) or []),
        connections_signal=tuple(js.jspath("$.ConnectionsSignal", list) or []),
        connections_group=tuple(js.jspath("$.ConnectionsGroup", list) or []),
        connections_signalgroup=tuple(js.jspath("$.ConnectionsSignalGroup", list) or []),
        path=dest or Path(file).parent,
    )

    return ss


def read_system_structure_xml(file: Path) -> dict[str, Any]:
    """Read the system structure in xml format and return as js5 dict, similar to ..._from_js5."""

    def type_value(el: ET.Element):
        typ = el.tag.split("}")[1]
        value = el.get("value")
        return {"Real": float, "Integer": int, "Boolean": bool, "String": str}[typ](value)

    el = read_xml(file)
    assert el.tag.endswith("OspSystemStructure"), f"<OspSystemStructure> expected. Found {el.tag}"
    ns = el.tag.split("{")[1].split("}")[0]
    bss = el.find(".//BaseStepSize") or 0.01
    header = {
        "xmlns": ns,
        "version": el.get("version", "'0.1'"),
        "StartTime": el.find(".//StartTime") or 0.0,
        "Algorithm": el.find(".//Algorithm") or "fixedStep",
        "BaseStepSize": bss,
    }

    simulators: dict = {}
    for sim in el.findall(".//{*}Simulator"):
        props = {
            "source": sim.get("source"),
            "stepSize": sim.get("stepSize", bss),
        }
        for initial in sim.findall(".//{*}InitialValue"):
            props.update({str(initial.get("variable")): type_value(initial[0])})
        assert "name" in sim.attrib, f"Required attribute 'name' not found in {sim.tag}, attrib:{sim.attrib}"
        simulators.update({sim.get("name"): props})

    structure = {"header": header, "Simulators": simulators}
    connections: dict = {}
    for c in ("Variable", "Signal", "Group", "SignalGroup"):
        cons: list = []
        for con in el.findall(".//{*}" + c + "Connection"):
            assert len(con) == 2, f"Two sub-elements expected. Found {len(con)}"
            _con: list = []
            for i in range(2):
                for p in con[i].attrib.values():
                    _con.append(p)
            cons.append(_con)
        if len(cons):
            connections.update({"Connections" + c: cons})
    if len(connections):
        structure.update(connections)

    return structure
