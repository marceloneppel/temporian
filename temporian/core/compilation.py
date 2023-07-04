# Copyright 2021 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from functools import wraps
from copy import copy
from typing import Any, Dict, Optional, Tuple
from temporian.core.data.node import Node
from temporian.implementation.numpy.data.event_set import EventSet


def compile(fn):
    """Compiles a Temporian function.

    A Temporian function is a function that takes Nodes as arguments and
    returns Nodes as outputs. Compiling it enables it to perform eager
    evaluation, i.e., receive and return EventSets instead of Nodes.

    Args:
        fn: The function to compile. The function must take Nodes as arguments
            (and may have other arguments of arbitrary types) and return Nodes
            as outputs.

    Returns:
        The compiled function.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        is_eager = None
        args = list(args)

        # Node -> EventSet mapping for eager evaluation
        inputs_map = {}

        for i, arg in enumerate(args):
            args[i], is_eager = _process_argument(
                arg, is_eager=is_eager, inputs_map=inputs_map
            )

        for k, arg in kwargs.items():
            kwargs[k], is_eager = _process_argument(
                arg, is_eager=is_eager, inputs_map=inputs_map
            )

        outputs = fn(*args, **kwargs)

        if is_eager:
            from temporian.core.evaluation import run

            return run(query=outputs, input=inputs_map)

        return outputs

    wrapper.is_tp_compiled = True

    return wrapper


def _process_argument(
    obj: Any,
    is_eager: Optional[bool],
    inputs_map: Dict[Node, EventSet],
) -> Tuple[Any, bool]:
    """Processes arguments to an operator by checking if its being used in eager
    mode and converting EventSets to Nodes if so.

    Also checks that all arguments are of the same type (EventSet or Node), by
    checking that is_eager is consistent with the type of obj, and raising if
    not.

    Note that the inputs_map is modified in-place by this function.
    """
    if isinstance(obj, tuple):
        obj = list(obj)
        for i, v in enumerate(obj):
            obj[i], is_eager = _process_argument(v, is_eager, inputs_map)
        return tuple(obj), is_eager

    if isinstance(obj, list):
        obj = copy(obj)
        for i, v in enumerate(obj):
            obj[i], is_eager = _process_argument(v, is_eager, inputs_map)
        return obj, is_eager

    if isinstance(obj, dict):
        obj = copy(obj)
        for k, v in obj.items():
            obj[k], is_eager = _process_argument(v, is_eager, inputs_map)
        return obj, is_eager

    err = (
        "Cannot mix EventSets and Nodes as inputs to an operator. Either get"
        " the node corresponding to each EventSet with .node(), or pass"
        " EventSets only."
    )

    if isinstance(obj, EventSet):
        if is_eager is None:
            is_eager = True
        elif not is_eager:
            # If a Node had been received and we receive an EventSet, raise
            raise ValueError(err)
        node = obj.node()
        # Its fine to overwrite the same node since the corresponding EventSet
        # is guaranteed to be the same one.
        inputs_map[node] = obj
        obj = node

    elif isinstance(obj, Node):
        if is_eager is None:
            is_eager = False
        elif is_eager:
            # If an EventSet had been received and we receive a Node, raise
            raise ValueError(err)

    return obj, is_eager