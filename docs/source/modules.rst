Modules documentation
=====================
This section documents the contents of the case_study package.


json5
-----
Python module for working with json5 files. 

.. autoclass:: case_study.json5.Json5
   :members:
   :show-inheritance:


Simulator Interface
-------------------
Python module providing the interface to the simulator. Currently only Open Simulation Platform (OSP) is supported

.. autoclass:: case_study.simulator_interface.SimulatorInterface
   :members:
   :show-inheritance:


Cases
--------
Python module to manage cases with respect to reading *.cases files, running cases and storing results

.. autoclass:: case_study.case.Cases
   :members:
   :show-inheritance:

.. autoclass:: case_study.case.Case
   :members:
   :show-inheritance:

.. autoclass:: case_study.case.Results
   :members:
   :show-inheritance:
