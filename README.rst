.. image:: https://img.shields.io/pypi/v/sim-explorer.svg?color=blue
   :target: https://pypi.org/project/sim-explorer
   :alt: pypi

.. image:: https://img.shields.io/pypi/pyversions/sim-explorer.svg?color=blue
   :target: https://pypi.org/project/sim-explorer
   :alt: versions

.. image:: https://img.shields.io/pypi/l/sim-explorer.svg
   :target: https://github.com/dnv-opensource/sim-explorer/blob/main/LICENSE
   :alt: license

.. image:: https://img.shields.io/github/actions/workflow/status/dnv-opensource/sim-explorer/.github%2Fworkflows%2Fnightly_build.yml?label=ci
   :alt: ci

.. image:: https://img.shields.io/github/actions/workflow/status/dnv-opensource/sim-explorer/.github%2Fworkflows%2Fpush_to_release.yml?label=docs
   :target: https://dnv-opensource.github.io/sim-explorer/README.html
   :alt: docs


Introduction
============
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

The package is designed as support tool for Assurance of Simulation Models, see `DNV-RP-0513 <https://standards.dnv.com/explorer/document/6A4F5922251B496B9216572C23730D33/2>`_.

The package is currently under development. More instructions and documentation will be added.

Installation
------------

``pip install sim-explorer``


Development Setup
-----------------

1. Install uv
^^^^^^^^^^^^^
This project uses `uv` as package manager.

If you haven't already, install `uv <https://docs.astral.sh/uv/>`_, preferably using it's `"Standalone installer" <https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_2/>`_ method:

..on Windows:

``powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"``

..on MacOS and Linux:

``curl -LsSf https://astral.sh/uv/install.sh | sh``

(see `docs.astral.sh/uv <https://docs.astral.sh/uv/getting-started/installation//>`_ for all / alternative installation methods.)

Once installed, you can update `uv` to its latest version, anytime, by running:

``uv self update``

2. Install Python
^^^^^^^^^^^^^^^^^
This project requires Python 3.10 or later.

If you don't already have a compatible version installed on your machine, the probably most comfortable way to install Python is through ``uv``:

``uv python install``

This will install the latest stable version of Python into the uv Python directory, i.e. as a uv-managed version of Python.

Alternatively, and if you want a standalone version of Python on your machine, you can install Python either via ``winget``:

``winget install --id Python.Python``

or you can download and install Python from the `python.org <https://www.python.org/downloads//>`_ website.

3. Clone the repository
^^^^^^^^^^^^^^^^^^^^^^^
Clone the sim-explorer repository into your local development directory:

``git clone https://github.com/dnv-opensource/sim-explorer path/to/your/dev/sim-explorer``

Change into the project directory after cloning:

``cd sim-explorer``

4. Install dependencies
^^^^^^^^^^^^^^^^^^^^^^^
Run ``uv sync`` to create a virtual environment and install all project dependencies into it:

``uv sync``

Note: Using ``--no-dev`` will omit installing development dependencies.

Note: ``uv`` will create a new virtual environment called ``.venv`` in the project root directory when running
``uv sync`` the first time. Optionally, you can create your own virtual environment using e.g. ``uv venv``, before running
``uv sync``.


5. (Optional) Activate the virtual environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
When using ``uv``, there is in almost all cases no longer a need to manually activate the virtual environment.

``uv`` will find the ``.venv`` virtual environment in the working directory or any parent directory, and activate it on the fly whenever you run a command via `uv` inside your project folder structure:

``uv run <command>``

However, you still *can* manually activate the virtual environment if needed.
When developing in an IDE, for instance, this can in some cases be necessary depending on your IDE settings.
To manually activate the virtual environment, run one of the "known" legacy commands:

..on Windows:

``.venv\Scripts\activate.bat``

..on Linux:

``source .venv/bin/activate``

6. Install pre-commit hooks
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The ``.pre-commit-config.yaml`` file in the project root directory contains a configuration for pre-commit hooks.
To install the pre-commit hooks defined therein in your local git repository, run:

``uv run pre-commit install``

All pre-commit hooks configured in ``.pre-commit-config.yam`` will now run each time you commit changes.

pre-commit can also manually be invoked, at anytime, using:

``uv run pre-commit run --all-files``

To skip the pre-commit validation on commits (e.g. when intentionally committing broken code), run:

``uv run git commit -m <MSG> --no-verify``

To update the hooks configured in `.pre-commit-config.yaml` to their newest versions, run:

``uv run pre-commit autoupdate``

7. Test that the installation works
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To test that the installation works, run pytest in the project root folder:

``uv run pytest``


Meta
----
Copyright (c) 2024 `DNV <https://www.dnv.com/>`_ AS. All rights reserved.

Siegfried Eisinger - siegfried.eisinger@dnv.com

Distributed under the MIT license. See `LICENSE <LICENSE.md/>`_ for more information.

`https://github.com/dnv-opensource/sim-explorer <https://github.com/dnv-opensource/sim-explorer/>`_

Contribute
----------
Anybody in the OSP community is welcome to contribute to this code, to make it better,
and especially including other features from model assurance,
as we firmly believe that trust in our models is needed
if we want to base critical decisions on the support from these models.


To contribute, follow these steps:

1. Fork it `<https://github.com/dnv-opensource/sim-explorer/fork/>`_
2. Create an issue in your GitHub repo
3. Create your branch based on the issue number and type (``git checkout -b issue-name``)
4. Evaluate and stage the changes you want to commit (``git add -i``)
5. Commit your changes (``git commit -am 'place a descriptive commit message here'``)
6. Push to the branch (``git push origin issue-name``)
7. Create a new Pull Request in GitHub

For your contribution, please make sure you follow the `STYLEGUIDE <STYLEGUIDE.md/>`_ before creating the Pull Request.
