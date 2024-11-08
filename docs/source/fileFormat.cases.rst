Cases file
==========
Cases specification is done using a json5-based format.
For an introduction to the basic json format see `here <https://en.wikipedia.org/wiki/JSON>`_.
Compared to that, the json5 variant has the following advantages

* object (dict) keys do not need quotation marks
* single and double quoted strings allowed
* optional trailing commas
* comments defined
* json5 files can readily be transformed to full json format
* jsonpath expressions working on the internal python representation work both on Json and Json5.

Json5 is also used in other software, like SQLite.
The main point for choosing json5 is thus its easier readability by humans,
while it is still readily readable by machines.

Cases files use the following general layout::

    {header : {
        name : exploration-project-name,
        variables : {
            alias-variable-definition-lines
        },
        optional-header-elements,
    },
    base : {
        optional description : "description-text",
        spec : {
            spec-lines,
        optional-results-list,
        optional-assert-sub-dict
    }},
    case-name : {
        case-specification-similar-to-base
    }
    # ... as many cases as desired
}

Header elements
---------------
The following header section elements (denoted as `header-lines` above) are defined

*name* (mandatory
    Name of the set of simulation experiments (cases)
*description* (optional
    Description of the simulation experiments defined here
*modelFile* (optional)
    The `OspSystemStructure.xml` file, the system relates to.
    A system model (OSP) is obviously needed. The following alternatives exist:

    * The co-simulation can be instantiated outside of cases and the `CosimExecution` object is provided as argument when instantiating `Cases`.
      In this case no `modelFile` is provided
    * If no `CosimExecution` object is provided, but a `OspSystemStructure.xml` file is found in the same folder as the `.cases` file,
      this file is assumed as the system definition file and a `CosimExecution` object is instantiated internally.
    * A system structure file can be explicitly specified and will be used to generate a `CosimExecution` object.
*logLevel* (optional)
    Log level of the simulator. Per default the level is set to FATAL,
    but it can be set to TRACE, DEBUG, INFO, WARNING, ERROR or FATAL (e.g. for debugging purposes)
*timeUnit* (optional)
    The unit of time the independent variable relates to, e.g. "second"
*variables* (mandatory)
    Definition of case variable names for use in the rest of the cases specification. See below.

Definition of case variables
----------------------------
The unique identification of a variable in a system requires an identificator containing both the component (instance) and the variable name (or reference).
The identificators can thus become lengthy and difficult to work with.
In addition, there are system models with several components from the same model, where the user might want to address all of them (e.g. max power setting of thrusters). Moreover, FMI2 knows only scalar variables, while it would be nice to also be able to work with vectors, tables and their elements.
Therefore sim explorer adops the principle that case variables are speparately defined.
The `variables` entry is a dictionary where each element is specified as

`identificator : [component(s), variable_name(s), description]`

In more detail

*identificator* (key, mandatory)
    Case variable identificator unique within the whole system.
    The identificator can in principle be any string, avoiding '.', '[]' and '@', but it is highly recommended to choose
    identificators complying to Python programming variable name rules
    (only ASCII letters, numbers and '_' are allowed and names shall not start with a number).
*component(s)* (mandatory)
    Component (instance) name as specified in the system description.
    If several components are specified the entry becomes a list and the components shall be based on the same model (FMU).
*variable_name(s)* (mandatory)
    Variable name as specified in the modelDescription of the component.
    If several variables are specified the entry becomes a list and the variables shall have
    the same properties with respect to type, causality and variability.
    For example `pos[\*]` denotes all elements of a vector if modelDescription specifies pos[0], pos[1] and pos[2].

    Note that it is not required that the units of the variables in the list are the same.
    For example a vector in spherical coordinates has length as first element and angle as second and third.
*description* (optional)
    Optionally a description string can be provided, explaining the meaning of the variable.

A few examples of case variable definitions are

* `g : ['bb', 'g', "Gravity acting on the ball"]`
* `p_max : [['thruster1','thruster2'], 'max_power', 'Maximum power setting of all thrusters in the system']`

   which could be abbreviated to

   `p_max : ['thruster\*, 'max_power, 'Maximum power setting of all thrusters in the system']`
* `pos : ['pendulum', ['pendulum_length', 'pendulum_polar', 'pendulum_azimuth'], 'Position of pendulum in spherical coordinates']`

   which could be abbreviated to

   `pos : ['pendulum', 'pendulum_\*', 'Position of pendulum in spherical coordinates']`

Case specification
------------------
A case specification consists of the elments

*description* (optional)
    A optional, but highly recommended description of the case can be provided
*parent* (optional)
    The parent case must be specified if a given case is based on another case.
    Otherwise a case is assumed to be based on the `base` case (see below).
    In this way a hierarchy of case specifications can be built.
    If this is done in a suitable way it can simplify case specifications considerably by avoiding a lot of double specification
    and possible errors due to changes in parent cases which are not reflected in their children.
    The special case `base` shall not have a parent (see below).
*spec* (mandatory)
    A dictionary of case variables and values, specifying the variable settings of the case, i.e. `variable : value(s)` . Details see below.
*results* (optional)
    An optional list of result variables (details see below)
*assert* (optional)
    An optional dictionary of assertion expressions, providing the possibility to automatically check model results. Details see below.


The mandatory case *base*:
^^^^^^^^^^^^^^^^^^^^^^^^^^
The base case, listing the base variable settings. All other cases are based on these settings.
It is not allowed to set variables in other cases if they are not set in the base case, as this would lead to moving targets,
i.e. the base case results would change after another case has been run.

It is recommended to specify all general results as part of the `base` specification (see below)

Within consistent case specifications all case variables are used in the cases `base` (avoid unused case variables)

and variables which are set in a case are always also set in the case `base` (avoid moving targets).

Specification of *results*:
^^^^^^^^^^^^^^^^^^^^^^^^^^^
As part of the case specification, it is also specified which results should be retrieved:

* All initial settings are automatically recorded at start time and are thus automaticaly included in the results Json5 file.
* A case may specify a `result` section, containing a list of result variables to be reported.

   Note that the variable specification consists only of case variables and no values and thus is represented by a  list, not a dictionary!
   In addition, Json rules imply that list values must include explicit quotation marks to be recognized as strings.
* A variable specification may use the string `'result'` or `'res'` to mark the respective variable as a result variable.
  If that syntax is used, the variable is a key, which does not need explicit quotation marks.


Variable specification
----------------------
In the simplest case a variable specification consists of a dictionary element

* `case_variable : value`,
* `case_variable : [value1, value2, ...]` in the case of a vector variable,
* `case_variable : 'result' or 'res'` within a normal case, representing a special result setting which applies to this case and all sub-cases,

   It is recommended that results specifications are mainly included in the base case, such that all cases report the same variables and can be readily compared.
   Only in special circumstances should other cases add variables to the results.

The variable name specification (the key) is much richer than the simple cases listed above. In general the `case_variable` can be replaced by

`case_variable[range]@time`

where `range` is either

* a list of integer indices.
* a python-like slice written as `int1..int2` or `int1...int2` , since `:` denote key separators and cannot be used inside a key.
  Note that slicing with negative integers (counting from end) is (currently) not implemented.

`@time` is an optional time specification where `time` is a float number.

Both extensions apply also to results specifications, i.e. results collection at given times.
With respect to results there is an additional keyword 'step' which can be used. `@step` leads to results collection at every communication point and
`@step interval` leads to results collection at the given fixed time interval.
`interval` is in this case a float number which should be larger than the basic time step.
It should be noted that step specifications do not change the simulation and results collections happen always at the first communication point after the time is due.

Simple example BouncingBall3D.cases
-----------------------------------
A simple example of a cases specification, based on the standard 3D BouncingBall FMU:

.. literalinclude:: ../../tests/data/BouncingBall3D/BouncingBall3D.cases
