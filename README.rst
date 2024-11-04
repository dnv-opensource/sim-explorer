.. !Only edit the file on the project root, as the one on docs/source is a copy!

************
Introduction
************
The package includes tools for experimentation on simulation models.
In the current version experimentation on top of OSP models is implemented.
The package introduces a json5-based file format for experiment specification.
Based on this specification

* a system model link is stored
* active variables are defined and alias names can be given
* the simulation base case variable settings are defined
* a hierarchy of sub-cases can be defined with their dedicated variable settings
* the common results to be retrieved from simulation runs is defined

Other features are

* alias variables can address multiple components of the same type, ensuring efficient experimentation.
* alias variables can vectors, even in FMI2 models. It is possible to set/get slices of such vectors
* variable settings can be time-based, enabling the definition of scenarios
* variable retrievals (results) can be time-based (in general and per case), enabling efficient model verification

The package does not support systematic variable sweep with respect to sets of variables. 
Such sweeps should be performed with separate tools. 
The package might be compared with navigating through a huge house, where the cases represent the various rooms, 
while searching for object in a given room is left to separate tools.

The package is designed as support tool for Assurance of Simulation Models, see DNV-RP-0513.

The package is currently under development. More instructions and documentation will be added.

Installation:
-------------
1.	Install the `sim-explorer` package: ``pip install sim-explorer``
2.	Software dependencies: `matplotlib`, `numpy`, `libcosimpy`, `jsonpath-ng`
3.	Latest release: Version 0.1, based on libcosimpy 0.0.2

Contribute
----------
Anybody in the OSP community is welcome to contribute to this code, to make it better, 
and especially including other features from model assurance, 
as we firmly believe that trust in our models is needed 
if we want to base critical decisions on the support from these models.
