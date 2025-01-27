import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from component_model.utils.xml import read_xml

from sim_explorer.json5 import Json5


# ==========================================
# Open Simulation Platform related functions
# ==========================================
def make_osp_system_structure(  # noqa: C901, PLR0913, PLR0915
    name: str = "OspSystemStructure",
    version: str = "0.1",
    start: float = 0.0,
    base_step: float = 0.01,
    algorithm: str = "fixedStep",  # noqa: ARG001
    simulators: dict[str, Any] | None = None,
    functions_linear: dict[str, Any] | None = None,
    functions_sum: dict[str, Any] | None = None,
    functions_vectorsum: dict[str, Any] | None = None,
    connections_variable: tuple[str, str, str, str] | None = None,  #: (model, out-variable, model, in-variable)
    connections_signal: tuple[str, str, str, str] | None = None,  #: (model, variable, function, signal)
    connections_group: tuple[str, str, str, str] | None = None,  #: (model, group, model, group)
    connections_signalgroup: tuple[str, str, str, str] | None = None,  #: (model, group, function, signal-group)
    path: Path | str = ".",
) -> Path:
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

    def element_text(
        tag: str,
        attr: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> ET.Element:
        el = ET.Element(tag=tag, attrib=attr or {})
        if text is not None:
            el.text = text
        return el

    def make_simulators(simulators: dict[str, Any] | None) -> ET.Element:
        """Make the <simulators> element (list of component models)."""

        def make_initial_value(
            var: str,
            val: int | float | bool | str,
        ) -> ET.Element:
            """Make a <InitialValue> element from the provided var dict."""
            typ: str = {int: "Integer", float: "Real", bool: "Boolean", str: "String"}[type(val)]
            initial: ET.Element = ET.Element(
                tag="InitialValue",
                attrib={"variable": var},
            )
            _ = ET.SubElement(
                parent=initial,
                tag=typ,
                attrib={"value": ("false", "true")[int(val)] if isinstance(val, bool) else str(val)},
            )
            return initial

        _simulators = ET.Element("Simulators")
        if simulators is not None:
            for m, props in simulators.items():
                simulator = ET.Element(
                    tag="Simulator",
                    attrib={
                        "name": m,
                        "source": props.get("source", m[0].upper() + m[1:] + ".fmu"),
                        "stepSize": str(props.get("stepSize", base_step)),
                    },
                )
                initial = ET.Element(tag="InitialValues")
                for var, value in props.items():
                    if var not in ("source", "stepSize"):
                        initial.append(make_initial_value(var, value))
                if len(initial):
                    simulator.append(initial)
                _simulators.append(simulator)
            # print(f"Model {m}: {simulator}. Length {len(simulators)}")  # noqa: ERA001
            # ET.ElementTree(simulators).write("Test.xml")  # noqa: ERA001
        return _simulators

    def make_functions(
        f_linear: dict[str, dict[str, Any]] | None,
        f_sum: dict[str, dict[str, Any]] | None,
        f_vectorsum: dict[str, dict[str, Any]] | None,
    ) -> ET.Element:
        _functions = ET.Element("Functions")
        key: str
        val: dict[str, Any]
        if f_linear is not None:
            for key, val in f_linear:
                _functions.append(
                    ET.Element(
                        tag="LinearTransformation",
                        attrib={
                            "name": key,
                            "factor": val["factor"],
                            "offset": val["offset"],
                        },
                    )
                )
        if f_sum is not None:
            for key, val in f_sum:
                _functions.append(
                    ET.Element(
                        tag="Sum",
                        attrib={
                            "name": key,
                            "inputCount": val["inputCount"],
                        },
                    ),
                )
        if f_vectorsum is not None:
            for key, val in f_vectorsum:
                _functions.append(
                    ET.Element(
                        tag="VectorSum",
                        attrib={
                            "name": key,
                            "inputCount": val["inputCount"],
                            "numericType": val["numericType"],
                            "dimension": val["dimension"],
                        },
                    )
                )
        return _functions

    def make_connections(
        c_variable: tuple[str, str, str, str] | None,
        c_signal: tuple[str, str, str, str] | None,
        c_group: tuple[str, str, str, str] | None,
        c_signalgroup: tuple[str, str, str, str] | None,
    ) -> ET.Element:
        """Make the <connections> element from the provided con."""

        def make_connection(
            main: str,
            sub1: str,
            attr1: dict[str, str],
            sub2: str,
            attr2: dict[str, str],
        ) -> ET.Element:
            el = ET.Element(tag=main)
            _ = ET.SubElement(parent=el, tag=sub1, attrib=attr1)
            _ = ET.SubElement(parent=el, tag=sub2, attrib=attr2)
            return el

        _cons = ET.Element(tag="Connections")
        m1: str
        v1: str
        g1: str
        m2: str
        v2: str
        g2: str
        f: str
        if c_variable is not None:
            for m1, v1, m2, v2 in c_variable:
                _cons.append(
                    make_connection(
                        main="VariableConnection",
                        sub1="Variable",
                        attr1={"simulator": m1, "name": v1},
                        sub2="Variable",
                        attr2={"simulator": m2, "name": v2},
                    )
                )
        if c_signal is not None:
            for m1, v1, f, v2 in c_signal:
                _cons.append(
                    make_connection(
                        main="SignalConnection",
                        sub1="Variable",
                        attr1={"simulator": m1, "name": v1},
                        sub2="Signal",
                        attr2={"function": f, "name": v2},
                    )
                )
        if c_group is not None:
            for m1, g1, m2, g2 in c_group:
                _cons.append(
                    make_connection(
                        main="VariableGroupConnection",
                        sub1="VariableGroup",
                        attr1={"simulator": m1, "name": g1},
                        sub2="VariableGroup",
                        attr2={"simulator": m2, "name": g2},
                    )
                )
        if c_signalgroup is not None:
            for m1, g1, f, g2 in c_signalgroup:
                _cons.append(
                    make_connection(
                        main="SignalGroupConnection",
                        sub1="VariableGroup",
                        attr1={"simulator": m1, "name": g1},
                        sub2="SignalGroup",
                        attr2={"function": f, "name": g2},
                    )
                )
        return _cons

    osp = ET.Element(
        tag="OspSystemStructure",
        attrib={
            "xmlns": "http://opensimulationplatform.com/MSMI/OSPSystemStructure",
            "version": version,
        },
    )
    osp.append(element_text(tag="StartTime", text=str(start)))
    osp.append(element_text(tag="BaseStepSize", text=str(base_step)))
    osp.append(make_simulators(simulators))
    osp.append(make_functions(functions_linear, functions_sum, functions_vectorsum))
    osp.append(make_connections(connections_variable, connections_signal, connections_group, connections_signalgroup))
    tree = ET.ElementTree(osp)
    ET.indent(tree, space="   ", level=0)
    file: Path = Path(path).absolute() / f"{name}.xml"
    tree.write(file, encoding="utf-8")
    return file


def osp_system_structure_from_js5(file: Path, dest: Path | None = None) -> Path:
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

    def type_value(el: ET.Element) -> int | float | bool | str:
        typ = el.tag.split("}")[1]
        value = el.get("value")
        return {"Integer": int, "Real": float, "Boolean": bool, "String": str}[typ](value)

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
            props[str(initial.get("variable"))] = type_value(initial[0])
        assert "name" in sim.attrib, f"Required attribute 'name' not found in {sim.tag}, attrib:{sim.attrib}"
        simulators[sim.get("name")] = props

    structure = {"header": header, "Simulators": simulators}
    connections: dict = {}
    for c in ("Variable", "Signal", "Group", "SignalGroup"):
        cons: list[list[str]] = []
        for con in el.findall(".//{*}" + c + "Connection"):
            assert len(con) == 2, f"Two sub-elements expected. Found {len(con)}"  # noqa: PLR2004
            cons.append([p for i in range(2) for p in con[i].attrib.values()])
        if len(cons):
            connections[f"Connections{c}"] = cons
    if len(connections):
        structure.update(connections)

    return structure
