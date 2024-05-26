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

Getting Started
===============
The project is under construction. Please consult the module documentation for more information.
TODO: Guide users through getting the code up and running on their own system 
and provide a step-by-step explanation how to instantiate a component model.

1.	Installation process
2.	Software dependencies
3.	Latest releases
4.	API references
5.  The cases specification format, see :

Build and Test
--------------
TODO: Describe and show how to build your code and run the tests. 

Contribute
----------
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)