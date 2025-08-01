import inspect
import os
import sys
import traceback
import reprlib

from enum import Enum
from itertools import islice
from types import FunctionType, MethodType
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

from . import cmd_with_io, parameters
from .debug import debug
from .parameters import DelayedEvaluationParameter, Parameter
from .exception import (
    MetaflowException,
    MissingInMergeArtifactsException,
    MetaflowInternalError,
    UnhandledInMergeArtifactsException,
)

from .extension_support import extension_info

from .graph import FlowGraph
from .unbounded_foreach import UnboundedForeachInput
from .user_configs.config_parameters import ConfigValue

from .user_decorators.mutable_flow import MutableFlow
from .user_decorators.mutable_step import MutableStep
from .user_decorators.user_flow_decorator import FlowMutator
from .user_decorators.user_step_decorator import StepMutator


from .util import to_pod
from .metaflow_config import INCLUDE_FOREACH_STACK, MAXIMUM_FOREACH_VALUE_CHARS

# For Python 3 compatibility
try:
    basestring
except NameError:
    basestring = str


from .datastore.inputs import Inputs

INTERNAL_ARTIFACTS_SET = set(
    [
        "_foreach_values",
        "_unbounded_foreach",
        "_control_mapper_tasks",
        "_control_task_is_mapper_zero",
        "_parallel_ubf_iter",
    ]
)


class InvalidNextException(MetaflowException):
    headline = "Invalid self.next() transition detected"

    def __init__(self, msg):
        # NOTE this assume that InvalidNextException is only raised
        # at the top level of next()
        _, line_no, _, _ = traceback.extract_stack()[-3]
        super(InvalidNextException, self).__init__(msg, line_no)


class ParallelUBF(UnboundedForeachInput):
    """
    Unbounded-for-each placeholder for supporting parallel (multi-node) steps.
    """

    def __init__(self, num_parallel):
        self.num_parallel = num_parallel

    def __getitem__(self, item):
        return item or 0  # item is None for the control task, but it is also split 0


class _FlowState(Enum):
    CONFIGS = 1
    FLOW_MUTATORS = 2
    CACHED_PARAMETERS = 3
    SET_CONFIG_PARAMETERS = (
        4  # These are Parameters that now have a ConfigValue (converted)
    )
    # but we need to remember them.


class FlowSpecMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name == "FlowSpec":
            return

        cls._init_attrs()

    def _init_attrs(cls):
        from .decorators import (
            DuplicateFlowDecoratorException,
        )  # Prevent circular import

        # We store some state in the flow class itself. This is primarily used to
        # attach global state to a flow. It is *not* an actual global because of
        # Runner/NBRunner. This is also created here in the meta class to avoid it being
        # shared between different children classes.

        # We should move _flow_decorators into this structure as well but keeping it
        # out to limit the changes for now.
        cls._flow_decorators = {}

        # Keys are _FlowState enum values
        cls._flow_state = {}

        # Keep track if configs have been processed -- this is particularly applicable
        # for the Runner/Deployer where calling multiple APIs on the same flow could
        # cause the configs to be processed multiple times. For a given flow, once
        # the configs have been processed, we do not process them again.
        cls._configs_processed = False

        # We inherit stuff from our parent classes as well -- we need to be careful
        # in terms of the order; we will follow the MRO with the following rules:
        #  - decorators (cls._flow_decorators) will cause an error if they do not
        #    support multiple and we see multiple instances of the same
        #  - config decorators will be joined
        #  - configs will be added later directly by the class; base class configs will
        #    be taken into account as they would be inherited.

        # We only need to do this for the base classes since the current class will
        # get updated as decorators are parsed.
        for base in cls.__mro__:
            if base != cls and base != FlowSpec and issubclass(base, FlowSpec):
                # Take care of decorators
                for deco_name, deco in base._flow_decorators.items():
                    if deco_name in cls._flow_decorators and not deco.allow_multiple:
                        raise DuplicateFlowDecoratorException(deco_name)
                    cls._flow_decorators.setdefault(deco_name, []).extend(deco)

                # Take care of configs and flow mutators
                base_configs = base._flow_state.get(_FlowState.CONFIGS)
                if base_configs:
                    cls._flow_state.setdefault(_FlowState.CONFIGS, {}).update(
                        base_configs
                    )
                base_mutators = base._flow_state.get(_FlowState.FLOW_MUTATORS)
                if base_mutators:
                    cls._flow_state.setdefault(_FlowState.FLOW_MUTATORS, []).extend(
                        base_mutators
                    )

        cls._init_graph()

    def _init_graph(cls):
        # Graph and steps are specific to the class -- store here so we can access
        # in class method _process_config_decorators
        cls._graph = FlowGraph(cls)
        cls._steps = [getattr(cls, node.name) for node in cls._graph]


class FlowSpec(metaclass=FlowSpecMeta):
    """
    Main class from which all Flows should inherit.

    Attributes
    ----------
    index
    input
    """

    # Attributes that are not saved in the datastore when checkpointing.
    # Name starting with '__', methods, functions and Parameters do not need
    # to be listed.
    _EPHEMERAL = {
        "_EPHEMERAL",
        "_NON_PARAMETERS",
        "_datastore",
        "_cached_input",
        "_graph",
        "_flow_decorators",
        "_flow_state",
        "_steps",
        "index",
        "input",
    }
    # When checking for parameters, we look at dir(self) but we want to exclude
    # attributes that are definitely not parameters and may be expensive to
    # compute (like anything related to the `foreach_stack`). We don't need to exclude
    # names starting with `_` as those are already excluded from `_get_parameters`.
    _NON_PARAMETERS = {"cmd", "foreach_stack", "index", "input", "script_name", "name"}

    def __init__(self, use_cli=True):
        """
        Construct a FlowSpec

        Parameters
        ----------
        use_cli : bool, default True
            Set to True if the flow is invoked from __main__ or the command line
        """

        self.name = self.__class__.__name__

        self._datastore = None
        self._transition = None
        self._cached_input = {}

        if use_cli:
            with parameters.flow_context(self.__class__) as _:
                from . import cli

                cli.main(self)

    @property
    def script_name(self) -> str:
        """
        [Legacy function - do not use. Use `current` instead]

        Returns the name of the script containing the flow

        Returns
        -------
        str
            A string containing the name of the script
        """
        fname = inspect.getfile(self.__class__)
        if fname.endswith(".pyc"):
            fname = fname[:-1]
        return os.path.basename(fname)

    @classmethod
    def _check_parameters(cls, config_parameters=False):
        seen = set()
        for _, param in cls._get_parameters():
            if param.IS_CONFIG_PARAMETER != config_parameters:
                continue
            norm = param.name.lower()
            if norm in seen:
                raise MetaflowException(
                    "Parameter *%s* is specified twice. "
                    "Note that parameter names are "
                    "case-insensitive." % param.name
                )
            seen.add(norm)

    @classmethod
    def _process_config_decorators(cls, config_options, process_configs=True):
        if cls._configs_processed:
            debug.userconf_exec("Mutating step/flow decorators already processed")
            return None
        cls._configs_processed = True

        # Fast path for no user configurations
        if not process_configs or (
            not cls._flow_state.get(_FlowState.FLOW_MUTATORS)
            and all(len(step.config_decorators) == 0 for step in cls._steps)
        ):
            # Process parameters to allow them to also use config values easily
            for var, param in cls._get_parameters():
                if isinstance(param, ConfigValue) or param.IS_CONFIG_PARAMETER:
                    continue
                param.init(not process_configs)
            return None

        debug.userconf_exec("Processing mutating step/flow decorators")
        # We need to convert all the user configurations from DelayedEvaluationParameters
        # to actual values so they can be used as is in the mutators.

        # We, however, need to make sure _get_parameters still works properly so
        # we store what was a config and has been set to a specific value.
        # This is safe to do for now because all other uses of _get_parameters typically
        # do not rely on the variable itself but just the parameter.
        to_save_configs = []
        cls._check_parameters(config_parameters=True)
        for var, param in cls._get_parameters():
            if not param.IS_CONFIG_PARAMETER:
                continue
            # Note that a config with no default and not required will be None
            val = config_options.get(param.name.replace("-", "_").lower())
            if isinstance(val, DelayedEvaluationParameter):
                val = val()
            # We store the value as well so that in _set_constants, we don't try
            # to recompute (no guarantee that it is stable)
            param._store_value(val)
            to_save_configs.append((var, param))
            debug.userconf_exec("Setting config %s to %s" % (var, str(val)))
            setattr(cls, var, val)

        cls._flow_state[_FlowState.SET_CONFIG_PARAMETERS] = to_save_configs
        # Run all the decorators. We first run the flow-level decorators
        # and then the step level ones to maintain a consistent order with how
        # other decorators are run.

        for deco in cls._flow_state.get(_FlowState.FLOW_MUTATORS, []):
            if isinstance(deco, FlowMutator):
                inserted_by_value = [deco.decorator_name] + (deco.inserted_by or [])
                mutable_flow = MutableFlow(
                    cls,
                    pre_mutate=True,
                    statically_defined=deco.statically_defined,
                    inserted_by=inserted_by_value,
                )
                # Sanity check to make sure we are applying the decorator to the right
                # class
                if not deco._flow_cls == cls and not issubclass(cls, deco._flow_cls):
                    raise MetaflowInternalError(
                        "FlowMutator registered on the wrong flow -- "
                        "expected %s but got %s"
                        % (deco._flow_cls.__name__, cls.__name__)
                    )
                debug.userconf_exec(
                    "Evaluating flow level decorator %s" % deco.__class__.__name__
                )
                deco.pre_mutate(mutable_flow)
                # We reset cached_parameters on the very off chance that the user added
                # more configurations based on the configuration
                if _FlowState.CACHED_PARAMETERS in cls._flow_state:
                    del cls._flow_state[_FlowState.CACHED_PARAMETERS]
            else:
                raise MetaflowInternalError(
                    "A non FlowMutator found in flow custom decorators"
                )

        for step in cls._steps:
            for deco in step.config_decorators:
                if isinstance(deco, StepMutator):
                    inserted_by_value = [deco.decorator_name] + (deco.inserted_by or [])
                    debug.userconf_exec(
                        "Evaluating step level decorator %s for %s"
                        % (deco.__class__.__name__, step.name)
                    )
                    deco.pre_mutate(
                        MutableStep(
                            cls,
                            step,
                            pre_mutate=True,
                            statically_defined=deco.statically_defined,
                            inserted_by=inserted_by_value,
                        )
                    )
                else:
                    raise MetaflowInternalError(
                        "A non StepMutator found in step custom decorators"
                    )

        # Process parameters to allow them to also use config values easily
        for var, param in cls._get_parameters():
            if param.IS_CONFIG_PARAMETER:
                continue
            param.init()

        # Set the current flow class we are in (the one we just created)
        parameters.replace_flow_context(cls)

        # Re-calculate class level attributes after modifying the class
        cls._init_graph()
        return cls

    def _set_constants(self, graph, kwargs, config_options):
        from metaflow.decorators import (
            flow_decorators,
        )  # To prevent circular dependency

        # Persist values for parameters and other constants (class level variables)
        # only once. This method is called before persist_constants is called to
        # persist all values set using setattr
        self._check_parameters(config_parameters=False)

        seen = set()
        self._success = True

        parameters_info = []
        for var, param in self._get_parameters():
            seen.add(var)
            if param.IS_CONFIG_PARAMETER:
                # Use computed value if already evaluated, else get from config_options
                val = param._computed_value or config_options.get(
                    param.name.replace("-", "_").lower()
                )
            else:
                val = kwargs[param.name.replace("-", "_").lower()]
            # Support for delayed evaluation of parameters.
            if isinstance(val, DelayedEvaluationParameter):
                val = val()
            val = val.split(param.separator) if val and param.separator else val
            if isinstance(val, ConfigValue):
                # We store config values as dict so they are accessible with older
                # metaflow clients. It also makes it easier to access.
                val = val.to_dict()
            setattr(self, var, val)
            parameters_info.append({"name": var, "type": param.__class__.__name__})

        # Do the same for class variables which will be forced constant as modifications
        # to them don't propagate well since we create a new process for each step and
        # re-read the flow file
        constants_info = []
        for var in dir(self.__class__):
            if var[0] == "_" or var in self._NON_PARAMETERS or var in seen:
                continue
            val = getattr(self.__class__, var)
            if isinstance(val, (MethodType, FunctionType, property, type)):
                continue
            constants_info.append({"name": var, "type": type(val).__name__})
            setattr(self, var, val)

        # We store the DAG information as an artifact called _graph_info
        steps_info, graph_structure = graph.output_steps()

        graph_info = {
            "file": os.path.basename(os.path.abspath(sys.argv[0])),
            "parameters": parameters_info,
            "constants": constants_info,
            "steps": steps_info,
            "graph_structure": graph_structure,
            "doc": graph.doc,
            "decorators": [
                {
                    "name": deco.name,
                    "attributes": to_pod(deco.attributes),
                    "statically_defined": deco.statically_defined,
                    "inserted_by": deco.inserted_by,
                }
                for deco in flow_decorators(self)
                if not deco.name.startswith("_")
            ]
            + [
                {
                    "name": deco.__class__.__name__,
                    "attributes": {},
                    "statically_defined": deco.statically_defined,
                    "inserted_by": deco.inserted_by,
                }
                for deco in self._flow_state.get(_FlowState.FLOW_MUTATORS, [])
            ],
            "extensions": extension_info(),
        }
        self._graph_info = graph_info

    @classmethod
    def _get_parameters(cls):
        cached = cls._flow_state.get(_FlowState.CACHED_PARAMETERS)
        returned = set()
        if cached is not None:
            for set_config in cls._flow_state.get(_FlowState.SET_CONFIG_PARAMETERS, []):
                returned.add(set_config[0])
                yield set_config[0], set_config[1]
            for var in cached:
                if var not in returned:
                    yield var, getattr(cls, var)
            return
        build_list = []
        for set_config in cls._flow_state.get(_FlowState.SET_CONFIG_PARAMETERS, []):
            returned.add(set_config[0])
            yield set_config[0], set_config[1]
        for var in dir(cls):
            if var[0] == "_" or var in cls._NON_PARAMETERS:
                continue
            try:
                val = getattr(cls, var)
            except:
                continue
            if isinstance(val, Parameter) and var not in returned:
                build_list.append(var)
                yield var, val
        cls._flow_state[_FlowState.CACHED_PARAMETERS] = build_list

    def _set_datastore(self, datastore):
        self._datastore = datastore

    def __iter__(self):
        """
        [Legacy function - do not use]

        Iterate over all steps in the Flow

        Returns
        -------
        Iterator[graph.DAGNode]
            Iterator over the steps in the flow
        """
        return iter(self._steps)

    def __getattr__(self, name: str):
        if self._datastore and name in self._datastore:
            # load the attribute from the datastore...
            x = self._datastore[name]
            # ...and cache it in the object for faster access
            setattr(self, name, x)
            return x
        else:
            raise AttributeError("Flow %s has no attribute '%s'" % (self.name, name))

    def cmd(self, cmdline, input={}, output=[]):
        """
        [Legacy function - do not use]
        """
        return cmd_with_io.cmd(cmdline, input=input, output=output)

    @property
    def index(self) -> Optional[int]:
        """
        The index of this foreach branch.

        In a foreach step, multiple instances of this step (tasks) will be executed,
        one for each element in the foreach. This property returns the zero based index
        of the current task. If this is not a foreach step, this returns None.

        If you need to know the indices of the parent tasks in a nested foreach, use
        `FlowSpec.foreach_stack`.

        Returns
        -------
        int, optional
            Index of the task in a foreach step.
        """
        if self._foreach_stack:
            return self._foreach_stack[-1].index

    @property
    def input(self) -> Optional[Any]:
        """
        The value of the foreach artifact in this foreach branch.

        In a foreach step, multiple instances of this step (tasks) will be executed,
        one for each element in the foreach. This property returns the element passed
        to the current task. If this is not a foreach step, this returns None.

        If you need to know the values of the parent tasks in a nested foreach, use
        `FlowSpec.foreach_stack`.

        Returns
        -------
        object, optional
            Input passed to the foreach task.
        """
        return self._find_input()

    def foreach_stack(self) -> Optional[List[Tuple[int, int, Any]]]:
        """
        Returns the current stack of foreach indexes and values for the current step.

        Use this information to understand what data is being processed in the current
        foreach branch. For example, considering the following code:
        ```
        @step
        def root(self):
            self.split_1 = ['a', 'b', 'c']
            self.next(self.nest_1, foreach='split_1')

        @step
        def nest_1(self):
            self.split_2 = ['d', 'e', 'f', 'g']
            self.next(self.nest_2, foreach='split_2'):

        @step
        def nest_2(self):
            foo = self.foreach_stack()
        ```

        `foo` will take the following values in the various tasks for nest_2:
        ```
            [(0, 3, 'a'), (0, 4, 'd')]
            [(0, 3, 'a'), (1, 4, 'e')]
            ...
            [(0, 3, 'a'), (3, 4, 'g')]
            [(1, 3, 'b'), (0, 4, 'd')]
            ...
        ```
        where each tuple corresponds to:

        - The index of the task for that level of the loop.
        - The number of splits for that level of the loop.
        - The value for that level of the loop.

        Note that the last tuple returned in a task corresponds to:

        - 1st element: value returned by `self.index`.
        - 3rd element: value returned by `self.input`.

        Returns
        -------
        List[Tuple[int, int, Any]]
            An array describing the current stack of foreach steps.
        """
        return [
            (frame.index, frame.num_splits, self._find_input(stack_index=i))
            for i, frame in enumerate(self._foreach_stack)
        ]

    def _find_input(self, stack_index=None):
        if stack_index is None:
            stack_index = len(self._foreach_stack) - 1

        if stack_index in self._cached_input:
            return self._cached_input[stack_index]
        elif self._foreach_stack:
            # NOTE this is obviously an O(n) operation which also requires
            # downloading the whole input data object in order to find the
            # right split. One can override this method with a more efficient
            # input data handler if this is a problem.
            frame = self._foreach_stack[stack_index]
            try:
                var = getattr(self, frame.var)
            except AttributeError:
                # this is where AttributeError happens:
                # [ foreach x ]
                #   [ foreach y ]
                #     [ inner ]
                #   [ join y ] <- call self.foreach_stack here,
                #                 self.x is not available
                self._cached_input[stack_index] = None
            else:
                try:
                    self._cached_input[stack_index] = var[frame.index]
                except TypeError:
                    # __getitem__ not supported, fall back to an iterator
                    self._cached_input[stack_index] = next(
                        islice(var, frame.index, frame.index + 1)
                    )
            return self._cached_input[stack_index]

    def merge_artifacts(
        self,
        inputs: Inputs,
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
    ) -> None:
        """
        Helper function for merging artifacts in a join step.

        This function takes all the artifacts coming from the branches of a
        join point and assigns them to self in the calling step. Only artifacts
        not set in the current step are considered. If, for a given artifact, different
        values are present on the incoming edges, an error will be thrown and the artifacts
        that conflict will be reported.

        As a few examples, in the simple graph: A splitting into B and C and joining in D:
        ```
        A:
          self.x = 5
          self.y = 6
        B:
          self.b_var = 1
          self.x = from_b
        C:
          self.x = from_c

        D:
          merge_artifacts(inputs)
        ```
        In D, the following artifacts are set:
          - `y` (value: 6), `b_var` (value: 1)
          - if `from_b` and `from_c` are the same, `x` will be accessible and have value `from_b`
          - if `from_b` and `from_c` are different, an error will be thrown. To prevent this error,
            you need to manually set `self.x` in D to a merged value (for example the max) prior to
            calling `merge_artifacts`.

        Parameters
        ----------
        inputs : Inputs
            Incoming steps to the join point.
        exclude : List[str], optional, default None
            If specified, do not consider merging artifacts with a name in `exclude`.
            Cannot specify if `include` is also specified.
        include : List[str], optional, default None
            If specified, only merge artifacts specified. Cannot specify if `exclude` is
            also specified.

        Raises
        ------
        MetaflowException
            This exception is thrown if this is not called in a join step.
        UnhandledInMergeArtifactsException
            This exception is thrown in case of unresolved conflicts.
        MissingInMergeArtifactsException
            This exception is thrown in case an artifact specified in `include` cannot
            be found.
        """
        include = include or []
        exclude = exclude or []
        node = self._graph[self._current_step]
        if node.type != "join":
            msg = (
                "merge_artifacts can only be called in a join and step *{step}* "
                "is not a join".format(step=self._current_step)
            )
            raise MetaflowException(msg)
        if len(exclude) > 0 and len(include) > 0:
            msg = "`exclude` and `include` are mutually exclusive in merge_artifacts"
            raise MetaflowException(msg)

        to_merge = {}
        unresolved = []
        for inp in inputs:
            # available_vars is the list of variables from inp that should be considered
            if include:
                available_vars = (
                    (var, sha)
                    for var, sha in inp._datastore.items()
                    if (var in include) and (not hasattr(self, var))
                )
            else:
                available_vars = (
                    (var, sha)
                    for var, sha in inp._datastore.items()
                    if (var not in exclude)
                    and (not hasattr(self, var))
                    and (var not in INTERNAL_ARTIFACTS_SET)
                )
            for var, sha in available_vars:
                _, previous_sha = to_merge.setdefault(var, (inp, sha))
                if previous_sha != sha:
                    # We have a conflict here
                    unresolved.append(var)
        # Check if everything in include is present in to_merge
        missing = []
        for v in include:
            if v not in to_merge and not hasattr(self, v):
                missing.append(v)
        if unresolved:
            # We have unresolved conflicts, so we do not set anything and error out
            msg = (
                "Step *{step}* cannot merge the following artifacts due to them "
                "having conflicting values:\n[{artifacts}].\nTo remedy this issue, "
                "be sure to explicitly set those artifacts (using "
                "self.<artifact_name> = ...) prior to calling merge_artifacts.".format(
                    step=self._current_step, artifacts=", ".join(unresolved)
                )
            )
            raise UnhandledInMergeArtifactsException(msg, unresolved)
        if missing:
            msg = (
                "Step *{step}* specifies that [{include}] should be merged but "
                "[{missing}] are not present.\nTo remedy this issue, make sure "
                "that the values specified in only come from at least one branch".format(
                    step=self._current_step,
                    include=", ".join(include),
                    missing=", ".join(missing),
                )
            )
            raise MissingInMergeArtifactsException(msg, missing)
        # If things are resolved, we pass down the variables from the input datastores
        for var, (inp, _) in to_merge.items():
            self._datastore.passdown_partial(inp._datastore, [var])

    def _validate_ubf_step(self, step_name):
        join_list = self._graph[step_name].out_funcs
        if len(join_list) != 1:
            msg = (
                "UnboundedForeach is supported only over a single node, "
                "not an arbitrary DAG. Specify a single `join` node"
                " instead of multiple:{join_list}.".format(join_list=join_list)
            )
            raise InvalidNextException(msg)
        join_step = join_list[0]
        join_node = self._graph[join_step]
        join_type = join_node.type

        if join_type != "join":
            msg = (
                "UnboundedForeach found for:{node} -> {join}."
                " The join type isn't valid.".format(node=step_name, join=join_step)
            )
            raise InvalidNextException(msg)

    def _get_foreach_item_value(self, item: Any):
        """
        Get the unique value for the item in the foreach iterator.  If no suitable value
        is found, return the value formatted by reprlib, which is at most 30 characters long.

        Parameters
        ----------
        item : Any
            The item to get the value from.

        Returns
        -------
        str
            The value to use for the item.
        """

        def _is_primitive_type(item):
            return (
                isinstance(item, basestring)
                or isinstance(item, int)
                or isinstance(item, float)
                or isinstance(item, bool)
            )

        value = item if _is_primitive_type(item) else reprlib.Repr().repr(item)
        return basestring(value)[:MAXIMUM_FOREACH_VALUE_CHARS]

    def next(self, *dsts: Callable[..., None], **kwargs) -> None:
        """
        Indicates the next step to execute after this step has completed.

        This statement should appear as the last statement of each step, except
        the end step.

        There are several valid formats to specify the next step:

        - Straight-line connection: `self.next(self.next_step)` where `next_step` is a method in
          the current class decorated with the `@step` decorator.

        - Static fan-out connection: `self.next(self.step1, self.step2, ...)` where `stepX` are
          methods in the current class decorated with the `@step` decorator.

        - Foreach branch:
          ```
          self.next(self.foreach_step, foreach='foreach_iterator')
          ```
          In this situation, `foreach_step` is a method in the current class decorated with the
          `@step` decorator and `foreach_iterator` is a variable name in the current class that
          evaluates to an iterator. A task will be launched for each value in the iterator and
          each task will execute the code specified by the step `foreach_step`.

        Parameters
        ----------
        dsts : Callable[..., None]
            One or more methods annotated with `@step`.

        Raises
        ------
        InvalidNextException
            Raised if the format of the arguments does not match one of the ones given above.
        """

        step = self._current_step

        foreach = kwargs.pop("foreach", None)
        num_parallel = kwargs.pop("num_parallel", None)
        if kwargs:
            kw = next(iter(kwargs))
            msg = (
                "Step *{step}* passes an unknown keyword argument "
                "'{invalid}' to self.next().".format(step=step, invalid=kw)
            )
            raise InvalidNextException(msg)

        # check: next() is called only once
        if self._transition is not None:
            msg = (
                "Multiple self.next() calls detected in step *{step}*. "
                "Call self.next() only once.".format(step=step)
            )
            raise InvalidNextException(msg)

        # check: all destinations are methods of this object
        funcs = []
        for i, dst in enumerate(dsts):
            try:
                name = dst.__func__.__name__
            except:
                msg = (
                    "In step *{step}* the {arg}. argument in self.next() is "
                    "not a function. Make sure all arguments in self.next() "
                    "are methods of the Flow class.".format(step=step, arg=i + 1)
                )
                raise InvalidNextException(msg)
            if not hasattr(self, name):
                msg = (
                    "Step *{step}* specifies a self.next() transition to an "
                    "unknown step, *{name}*.".format(step=step, name=name)
                )
                raise InvalidNextException(msg)
            funcs.append(name)

        if num_parallel is not None and num_parallel >= 1:
            if len(dsts) > 1:
                raise InvalidNextException(
                    "Only one destination allowed when num_parallel used in self.next()"
                )
            foreach = "_parallel_ubf_iter"
            self._parallel_ubf_iter = ParallelUBF(num_parallel)

        # check: foreach is valid
        if foreach:
            if not isinstance(foreach, basestring):
                msg = (
                    "Step *{step}* has an invalid self.next() transition. "
                    "The argument to 'foreach' must be a string.".format(step=step)
                )
                raise InvalidNextException(msg)

            if len(dsts) != 1:
                msg = (
                    "Step *{step}* has an invalid self.next() transition. "
                    "Specify exactly one target for 'foreach'.".format(step=step)
                )
                raise InvalidNextException(msg)

            try:
                foreach_iter = getattr(self, foreach)
            except:
                msg = (
                    "Foreach variable *self.{var}* in step *{step}* "
                    "does not exist. Check your variable.".format(
                        step=step, var=foreach
                    )
                )
                raise InvalidNextException(msg)
            self._foreach_values = None
            if issubclass(type(foreach_iter), UnboundedForeachInput):
                self._unbounded_foreach = True
                self._foreach_num_splits = None
                self._validate_ubf_step(funcs[0])
            else:
                try:
                    if INCLUDE_FOREACH_STACK:
                        self._foreach_values = []
                        for item in foreach_iter:
                            value = self._get_foreach_item_value(item)
                            self._foreach_values.append(value)
                        self._foreach_num_splits = len(self._foreach_values)
                    else:
                        self._foreach_num_splits = sum(1 for _ in foreach_iter)
                except Exception as e:
                    msg = (
                        "Foreach variable *self.{var}* in step *{step}* "
                        "is not iterable. Please check details: {err}".format(
                            step=step, var=foreach, err=str(e)
                        )
                    )
                    raise InvalidNextException(msg)

                if self._foreach_num_splits == 0:
                    msg = (
                        "Foreach iterator over *{var}* in step *{step}* "
                        "produced zero splits. Check your variable.".format(
                            step=step, var=foreach
                        )
                    )
                    raise InvalidNextException(msg)

            self._foreach_var = foreach

        # check: non-keyword transitions are valid
        if foreach is None:
            if len(dsts) < 1:
                msg = (
                    "Step *{step}* has an invalid self.next() transition. "
                    "Specify at least one step function as an argument in "
                    "self.next().".format(step=step)
                )
                raise InvalidNextException(msg)

        self._transition = (funcs, foreach)

    def __str__(self):
        step_name = getattr(self, "_current_step", None)
        if step_name:
            index = ",".join(str(idx) for idx, _, _ in self.foreach_stack())
            if index:
                inp = self.input
                if inp is None:
                    return "<flow %s step %s[%s]>" % (self.name, step_name, index)
                else:
                    inp = str(inp)
                    if len(inp) > 20:
                        inp = inp[:20] + "..."
                    return "<flow %s step %s[%s] (input: %s)>" % (
                        self.name,
                        step_name,
                        index,
                        inp,
                    )
            else:
                return "<flow %s step %s>" % (self.name, step_name)
        else:
            return "<flow %s>" % self.name

    def __getstate__(self):
        raise MetaflowException(
            "Flows can't be serialized. Maybe you tried "
            "to assign *self* or one of the *inputs* "
            "to an attribute? Instead of serializing the "
            "whole flow, you should choose specific "
            "attributes, e.g. *input.some_var*, to be "
            "stored."
        )
