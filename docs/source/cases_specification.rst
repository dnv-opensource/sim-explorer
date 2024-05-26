Cases specification format
==========================
Cases specification is done using a json5-based format. 
For an itroduction to the basic json format see `here <https://en.wikipedia.org/wiki/JSON>`_.
Compared to that, the json5 variant has the following advantages

* object (dict) keys do not need quotation marks
* single and double quoted strings allowed
* optional trailing commas
* comments defined
* json5 files can readily be transformed to full json format

Json5 is also used in other software, like SQLite.
The main point for choosing json5 is thus its easier readability by humans,
while it is still readily readable by machines.

Cases files use the following general layout::

    {header-lines,
    variables : {
        alias-variable-definition-lines
    },
    base : {
        optional description : "description-text",
        spec : {
            spec-lines,
    }},
    case-name : {
        case-specification-similar-to-base
    }
    # ... as many cases as desired
    results : {
        spec : [ # Note: this is a list of keys, as there are no values
            results-spec-lines,   
    ]}}

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
*timeUnit* (optional)
    The unit of time the independent variable relates to, e.g. "second"
*variables* (mandatory)
    Definition of case variable names for use in the rest of the cases specification. See below. 

Definition of case variables
----------------------------
The unique identification of a variable in a system requires an identificator containing both the component (instance) and the variable name (or reference).
The identificators can thus become lengthy and difficult to work with. 
In addition, there are system models with several components from the same model, where the user might want to address all of them (e.g. max power setting of thrusters). Moreover, FMI2 knows only scalar variables, while it would be nice to also be able to work with vectors, tables and their elements. 
Therefore case study adops the principle that case variables are speparately defined. 
The `variables` entry is a dictionary where one element is specified as

`identificator : [component(s), variable_name(s), description]` 

In more details

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
    Note that it is not required that the units of the variables in the list are the same. 
    For example a vector in spherical coordinates has length as first element and angle as second and third.
*description* (optional)
    Optionally a description string can be provided, explaining the meaning of the variable.

A few examples of case variable definitions are

* `g : ['bb', 'g', "Gravity acting on the ball"]`
* `p_max : [['thruster1','thruster2'], 'max_power', 'Maximum power setting of all thrusters in the system']`
* `pos : ['pendulum', ['pendulum_length', 'pendulum_polar', 'pendulum_azimuth'], 'Position of pendulum in spherical coordinates']`

Case specification
------------------
A case specification conists of the elments

*description* (optional)
    A optional, but highly recommended description of the case can be provided
*parent* (optional)
    The parent case must be specified if a given case is based on another case. 
    Otherwise a case is assumed to be based on the `base` case (see below).
    In this way a hierarchy of case specifications can be built. 
    If this is done in a suitable way it can simplify case specifications considerably by avoiding a lot of double specification
    and possible errors due to changes in paren cases which are not reflected in their children.
    The special cases `base` and `results` shall not have parents (see below).
*spec* (mandatory)
    A dictionary of case variables and values, specifying the variable settings of the case, i.e. `variable : value(s)` . Details see below.


There are two special, mandatory cases:

*base*
    the base case, listing the base variable settings. All other cases are based on these settings. 
    It is not allowed to set variables in other cases if they are not set in the base case, as this would lead to moving targets, 
    i.e. the base case results would change after another case has been run.
*results*
    listing of results variables. 
    Note that the variable specification consists only of case variables and no values and thus is represented by a  list, not a dictionary!

Within consistent case specifications all case variables are used in the cases `base` or `results` (avoid unused case variables) 
and variables which are set in a case are always also set in the case `base` (avoid moving targets).

Variable specification
----------------------
In the simplest case a variable specification consists of a dictionary element

* `case_variable : value`, 
* `case_variable : [value1, value2, ...]` in the case of a vector variable, 
* avoiding the value(s) altogether in the case of results specifications (see above) or
* `case_variable : 'NoValue'` within a normal case, representing a special result setting which applies only to this case,
  i.e. only for the respective case this result is recorded. 
  This setting should be used with care, since it is normally desired to have the same results setup for all cases, such that all cases can be compared.

The variable name specification (the key) is much richer than the simple cases listed above. In general the `case_variable` can be replaced by

`case_variable[range]@time`

where `range` is either a python-like slice, or a list of integer indices. `@time` is an optional time specification where `time` is a float number. 
Both extensions apply also to results specifications, i.e. results collection at given times. 
With respect to results there is an additional keyword 'step' which can be used. `@step` leads to results collection at every communication point and 
`@step interval` leads to results collection at the given fixed time interval. 
`interval` is in this case a float number which should be larger than the basic time step. 
It should be noted step specifications do not change the simulation and results collections happen always at the first communication point after the time is due.

Simple example BouncingBall.cases
---------------------------------
A simple example of a cases specification, based on the standard BouncingBall FMU::

    {name        : 'BouncingBall',
     description : 'Simple Case Study with the basic BouncingBall FMU (ball dropped from h=1m',
     modelFile : "OspSystemStructure.xml",
     timeUnit  : "second",
     variables : {
         g : ['bb', 'g', "Gravity acting on the ball"],
         e : ['bb', 'e', "Coefficient of restitution"],
    },
    base : {
        description : "Variable settings for the base case. All other cases are based on that",
        spec: {
            stepSize : 0.1,
            stopTime : '3',
            g        : -9.81,
    }},
    case1 : {
        description : "Smaller coefficient of restitution e",
        spec: {
        e : 0.35,
        e@1 : 0.5, # change restitution at time 1
    }},
    case2 : {
        description : "Based case1 (e change), change also the gravity g",
        parent : 'case1',
        spec : {
            g : -1.5
    }},
    # ... other case definitions
    results : {
        spec : [
            h@step, # example of 'h' at every communication point
            v@1.0, # example of result only at time 1
            e,
            g,
   ]}}
