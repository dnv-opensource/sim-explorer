import logging
from pathlib import Path

from ax import (
    Experiment,
    Objective,
    OptimizationConfig,
)

# Ax imports
from ax.modelbridge.generation_strategy import GenerationStep, GenerationStrategy
from ax.modelbridge.registry import Models
from ax.service.scheduler import Scheduler, SchedulerOptions
from ax.service.utils.instantiation import InstantiationBase
from ax.utils.common.logger import ROOT_STREAM_HANDLER

# Our libraries
from libcosimpy.CosimEnums import CosimVariableCausality
from libcosimpy.CosimLogging import CosimLogLevel, log_output_level
from signal_tl import Always, Eventually, Predicate

from mvx.metrics.osp import SimulatorMetric
from mvx.runners.simulator_runners.base import SimulatorRunner
from mvx.simulators.base import Variable
from mvx.simulators.osp import OSPSimulator

# Creating a simulator metric
from mvx.utils.functions.osp import STLRobustness

ROOT_STREAM_HANDLER.setLevel(logging.WARNING)
ROOT_PATH = Path("").absolute().parent.parent
log_output_level(CosimLogLevel.WARNING)  # possible values: TRACE, INFO or DEBUG, WARNING, ERROR

# Create a simulator
h = Variable(name="h", instance="bb", causality=CosimVariableCausality.OUTPUT)
simulator = OSPSimulator(
    system_path=f"{ROOT_PATH}/tests/data/BouncingBall/OspSystemStructure.xml", observed_variables=[h]
)

# Setting a parameter to vary
parameters = [{"name": "bb.e", "type": "range", "value_type": "float", "bounds": [0.5, 0.76]}]

# Create a search space
search_space = InstantiationBase.make_search_space(parameters, None)

# Define an STL specification
a = Predicate("bb.h") <= 0.01

# FG(h <= 0.01): the ball will be stationary within 3 seconds
phi = Eventually(Always(a))

robustness_func = STLRobustness(spec=phi)

optimization_config = OptimizationConfig(
    objective=Objective(
        metric=SimulatorMetric(name="qt_sim", simulator=simulator, result_evaluation=robustness_func, step_count=300),
        minimize=True,
    )
)

# Creating an experiment that uses:
# 1. Search space
# 2. Optimization config
# 3. Simulator runner
# step_count = 300 - 3 seconds
experiment = Experiment(
    name="runner_test",
    search_space=search_space,
    optimization_config=optimization_config,
    runner=SimulatorRunner(simulator=simulator, step_count=300),
    properties={"immutable_search_space_and_opt_config": True},
)

# Number of trials to perform
MAX_TRIALS = 20

# Generation strategy that chains two steps:
# 1. Sobol sampling without pre-existing data
# 2. Bayesian optimization via GPEI method
gs = GenerationStrategy(
    steps=[
        # 1. Initialization step (does not require pre-existing data and is well-suited for
        # initial sampling of the search space)
        GenerationStep(
            model=Models.SOBOL,
            num_trials=5,  # How many trials should be produced from this generation step
            min_trials_observed=3,  # How many trials need to be completed to move to next model
            max_parallelism=5,  # Max parallelism for this step
            model_kwargs={"seed": 999},  # Any kwargs you want passed into the model
            model_gen_kwargs={},  # Any kwargs you want passed to `modelbridge.gen`
        ),
        # 2. Bayesian optimization step (requires data obtained from previous phase and learns
        # from all data available at the time of each new candidate generation call)
        GenerationStep(
            model=Models.GPEI,
            num_trials=-1,  # No limitation on how many trials should be produced from this step
            max_parallelism=1,  # Parallelism limit for this step, often lower than for Sobol
            # More on parallelism vs. required samples in BayesOpt:
            # https://ax.dev/docs/bayesopt.html#tradeoff-between-parallelism-and-total-number-of-trials
        ),
    ]
)

scheduler_options = SchedulerOptions()
scheduler = Scheduler(
    experiment=experiment,
    generation_strategy=gs,
    options=scheduler_options,
)
scheduler.logger.setLevel(logging.WARNING)  # type: ignore
print("NOW RUNNING")
_ = scheduler.run_n_trials(max_trials=MAX_TRIALS)
# pass
