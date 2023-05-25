# Copyright (c) 2021 - present / Neuralmagic, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import logging
import os
import tempfile
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple, Union

import numpy
import onnx
from onnx.mapping import TENSOR_TYPE_TO_NP_TYPE

from deepsparse.utils.extractor import Extractor
from sparsezoo.utils import save_onnx, validate_onnx


try:
    from sparsezoo import File, Model

    sparsezoo_import_error = None
except Exception as sparsezoo_err:
    Model = object
    File = object
    sparsezoo_import_error = sparsezoo_err

__all__ = [
    "model_to_path",
    "get_external_inputs",
    "get_external_outputs",
    "get_input_names",
    "get_output_names",
    "generate_random_inputs",
    "override_onnx_batch_size",
    "override_onnx_input_shapes",
    "truncate_onnx_model",
    "truncate_onnx_embedding_model",
]

_LOGGER = logging.getLogger(__name__)


@contextlib.contextmanager
def save_onnx_to_temp_files(model: Model) -> str:
    """
    Save model to a temporary file.  Works for models with external data.
    """
    shaped_model = tempfile.NamedTemporaryFile(mode="w", delete=False)
    external_data = next(tempfile._get_candidate_names())
    has_external_data = save_onnx(model, shaped_model.name, external_data)

    try:
        yield shaped_model.name
    finally:
        os.unlink(shaped_model.name)
        shaped_model.close()
        if has_external_data:
            external_data_path = os.path.join(
                os.path.dirname(shaped_model.name), external_data
            )
            os.unlink(external_data_path)


def translate_onnx_type_to_numpy(tensor_type: int):
    """
    Translates ONNX types to numpy types
    :param tensor_type: Integer representing a type in ONNX spec
    :return: Corresponding numpy type
    """
    if tensor_type not in TENSOR_TYPE_TO_NP_TYPE:
        raise Exception("Unknown ONNX tensor type = {}".format(tensor_type))
    return TENSOR_TYPE_TO_NP_TYPE[tensor_type]


def model_to_path(model: Union[str, Model, File]) -> str:
    """
    Deals with the various forms a model can take. Either an ONNX file,
    a SparseZoo model stub prefixed by 'zoo:', a SparseZoo Model object,
    or a SparseZoo ONNX File object that defines the neural network. Noting
    the model will be downloaded automatically if a SparseZoo stub is passed

    :param model: Either a local str path or SparseZoo stub to the model. Can
        also be a sparsezoo.Model or sparsezoo.File object
    :returns: The absolute local str path to the model
    """
    if not model:
        raise ValueError("model must be a path, sparsezoo.Model, or sparsezoo.File")

    if isinstance(model, str) and model.startswith("zoo:"):
        # load SparseZoo Model from stub
        if sparsezoo_import_error is not None:
            raise sparsezoo_import_error
        model = Model(model)

    if Model is not object and isinstance(model, Model):
        # default to the main onnx file for the model
        model = model.onnx_model.path
    elif File is not object and isinstance(model, File):
        # get the downloaded_path -- will auto download if not on local system
        model = model.path

    if not isinstance(model, str):
        raise ValueError("unsupported type for model: {}".format(type(model)))

    if not os.path.exists(model):
        raise ValueError("model path must exist: given {}".format(model))

    return model


def get_external_inputs(onnx_filepath: str) -> List:
    """
    Gather external inputs of ONNX model
    :param onnx_filepath: File path to ONNX model
    :return: List of input objects
    """
    model = onnx.load(onnx_filepath, load_external_data=False)
    all_inputs = model.graph.input
    initializer_input_names = [node.name for node in model.graph.initializer]
    external_inputs = [
        input for input in all_inputs if input.name not in initializer_input_names
    ]
    return external_inputs


def get_external_outputs(onnx_filepath: str) -> List:
    """
    Gather external outputs of ONNX model
    :param onnx_filepath: File path to ONNX model
    :return: List of output objects
    """
    model = onnx.load(onnx_filepath, load_external_data=False)
    return [output for output in model.graph.output]


def get_input_names(onnx_filepath: str) -> List[str]:
    """
    Gather names of all external inputs of ONNX model
    :param onnx_filepath: File path to ONNX model
    :return: List of string names
    """
    return [input_.name for input_ in get_external_inputs(onnx_filepath)]


def get_output_names(onnx_filepath: str) -> List[str]:
    """
    Gather names of all external outputs of ONNX model
    :param onnx_filepath: File path to ONNX model
    :return: List of string names
    """
    return [output.name for output in get_external_outputs(onnx_filepath)]


def generate_random_inputs(
    onnx_filepath: str, batch_size: int = None
) -> List[numpy.array]:
    """
    Generate random data that matches the type and shape of ONNX model,
    with a batch size override
    :param onnx_filepath: File path to ONNX model
    :param batch_size: If provided, override for the batch size dimension
    :return: List of random tensors
    """
    input_data_list = []
    for i, external_input in enumerate(get_external_inputs(onnx_filepath)):
        input_tensor_type = external_input.type.tensor_type
        elem_type = translate_onnx_type_to_numpy(input_tensor_type.elem_type)
        in_shape = [int(d.dim_value) for d in input_tensor_type.shape.dim]

        if batch_size is not None:
            in_shape[0] = batch_size

        _LOGGER.info(
            "Generating input '{}', type = {}, shape = {}".format(
                external_input.name, numpy.dtype(elem_type).name, in_shape
            )
        )
        input_data_list.append(numpy.random.rand(*in_shape).astype(elem_type))
    return input_data_list


def override_onnx_batch_size(
    onnx_filepath: str, batch_size: int, inplace: bool = False
) -> str:
    """
    Rewrite batch sizes of ONNX model, saving the modified model and returning its path
    :param onnx_filepath: File path to ONNX model
    :param batch_size: Override for the batch size dimension
    :param inplace: If True, overwrite the original model file
    :return: File path to modified ONNX model
    """
    model = onnx.load(onnx_filepath, load_external_data=False)
    all_inputs = model.graph.input
    initializer_input_names = [node.name for node in model.graph.initializer]
    external_inputs = [
        input for input in all_inputs if input.name not in initializer_input_names
    ]
    for external_input in external_inputs:
        external_input.type.tensor_type.shape.dim[0].dim_value = batch_size

    if inplace:
        onnx.save(model, onnx_filepath)
        return onnx_filepath
    else:
        # Save modified model, this will be cleaned up when context is exited
        return save_onnx_to_temp_files(model)


def override_onnx_input_shapes(
    onnx_filepath: str,
    input_shapes: Union[List[int], List[List[int]]],
    inplace: bool = False,
) -> str:
    """
    Rewrite input shapes of ONNX model, saving the modified model and returning its path
    :param onnx_filepath: File path to ONNX model
    :param input_shapes: Override for model's input shapes
    :param inplace: If True, overwrite the original model file
    :return: File path to modified ONNX model
    """

    if input_shapes is None:
        return onnx_filepath

    model = onnx.load(onnx_filepath, load_external_data=False)
    all_inputs = model.graph.input
    initializer_input_names = [node.name for node in model.graph.initializer]
    external_inputs = [
        input for input in all_inputs if input.name not in initializer_input_names
    ]

    # Input shapes should be a list of lists, even if there is only one input
    if not all(isinstance(inp, list) for inp in input_shapes):
        input_shapes = [input_shapes]

    # If there is a single input shape given and multiple inputs,
    # duplicate for all inputs to apply the same shape
    if len(input_shapes) == 1 and len(external_inputs) > 1:
        input_shapes.extend([input_shapes[0] for _ in range(1, len(external_inputs))])

    # Make sure that input shapes can map to the ONNX model
    assert len(external_inputs) == len(
        input_shapes
    ), "Mismatch of number of model inputs ({}) and override shapes ({})".format(
        len(external_inputs), len(input_shapes)
    )

    # Overwrite the input shapes of the model
    for input_idx, external_input in enumerate(external_inputs):
        assert len(external_input.type.tensor_type.shape.dim) == len(
            input_shapes[input_idx]
        ), "Input '{}' shape doesn't match shape override: {} vs {}".format(
            external_input.name,
            external_input.type.tensor_type.shape.dim,
            input_shapes[input_idx],
        )
        for dim_idx, dim in enumerate(external_input.type.tensor_type.shape.dim):
            dim.dim_value = input_shapes[input_idx][dim_idx]

    if inplace:
        onnx.save(model, onnx_filepath)
        return onnx_filepath
    else:
        # Save modified model, this will be cleaned up when context is exited
        return save_onnx_to_temp_files(model)


def truncate_onnx_model(
    onnx_filepath: str,
    output_filepath: str,
    final_node_names: List[str],
    graph_output_names: List[str],
    graph_output_shapes: Optional[List[List[int]]] = None,
) -> None:
    """
    :param onnx_filepath: file path to onnx model
    :param output_filepath: file path to save new onnx model
    :param final_node_names: list of node names whose outputs will become the
        outputs of the graph
    :param graph_output_names: list of names to call the graph outputs. Names
        correspond with the outputs specified in final_node_names
    :param graph_output_shapes: list of shapes for each output. If not provided,
        defaults to [None] for each output and leads to slight performance loss
    :return: None
    """
    if graph_output_shapes is None:
        graph_output_shapes = [None] * len(final_node_names)

    if len(final_node_names) != len(graph_output_names) != len(graph_output_shapes):
        raise ValueError(
            f"length of final_node_names {len(final_node_names)}, "
            f"graph_output_names {len(graph_output_names)}, and "
            f"graph_output_shapes {len(graph_output_shapes)} must all match"
        )

    if len(set(final_node_names)) != len(final_node_names):
        raise ValueError("final_node_names must not contain duplicate names")

    if len(set(graph_output_names)) != len(graph_output_names):
        raise ValueError("graph_output_names must not contain duplicate names")

    model = onnx.load(onnx_filepath)
    final_nodes = [node for node in model.graph.node if node.name in final_node_names]

    if len(final_nodes) != len(final_node_names):
        raise ValueError("Could not find final node names in model graph")

    for final_node, graph_output_name, graph_output_shape in zip(
        final_nodes, graph_output_names, graph_output_shapes
    ):
        # write each node's output to new output
        [final_node.output.pop() for _ in final_node.output]
        final_node.output.append(graph_output_name)

        # write graph output. TODO: use ort to find real shapes and types
        output_value_info = onnx.helper.make_tensor_value_info(
            graph_output_name, onnx.TensorProto.UNDEFINED, graph_output_shape
        )
        model.graph.output.append(output_value_info)

    # collect graph inputs
    graph_input_names = [input.name for input in model.graph.input]

    # use extractor to create and write subgraph
    original_num_nodes = len(model.graph.node)
    extractor = Extractor(model)
    extracted_model = extractor.extract_model(
        input_names=graph_input_names, output_names=graph_output_names
    )
    extracted_num_nodes = len(extracted_model.graph.node)
    _LOGGER.info(
        f"Truncating model graph to {final_node_names}. "
        f"Removed {original_num_nodes - extracted_num_nodes} nodes, "
        f"{extracted_num_nodes} remaining"
    )

    for output in extracted_model.graph.output:
        if len(output.type.tensor_type.shape.dim) == 0:
            # ONNX checker treats None shapes and empty shapes
            # differently, clear None shape to pass checker
            output.type.tensor_type.shape.Clear()

    # save and check model
    save_onnx(extracted_model, output_filepath, "external_data")
    validate_onnx(output_filepath)


def truncate_onnx_embedding_model(
    model_path: str,
    emb_extraction_layer: Union[int, str, None] = None,
    output_filepath: Optional[str] = None,
) -> Tuple[str, Optional[NamedTemporaryFile]]:
    """
     :param model_path: path of onnx file to be cut
    :param emb_extraction_layer: if an int, last layer to include. If a
        string, then the name of the last node in the truncated graph.
        default is None.
    :param output_filepath: path to write resulting onnx file. If not provided,
        will create a temporary file path that will be destroyed on program end
    :return: if no output path, a tuple of the saved path to the model, list of
        model output names, and reference to the tempfile object will be returned
        otherwise, a tuple containing the given output_path argument, the model
        output names, and None
    """

    tmp_file = None
    if output_filepath is None:
        tmp_file = NamedTemporaryFile()
        output_filepath = tmp_file.name

    # determine where to cut the model
    model = onnx.load(model_path)
    if isinstance(emb_extraction_layer, str):
        final_node = None
        for graph_node in model.graph.node:
            if graph_node.name == emb_extraction_layer:
                final_node = graph_node

        if final_node is None:
            raise RuntimeError(
                f"Unable to find node {emb_extraction_layer} for extraction in graph"
            )

        final_node_name = final_node.name
        graph_output_name = final_node.output[0]
    else:
        final_node_name = model.graph.node[emb_extraction_layer].name
        graph_output_name = model.graph.node[emb_extraction_layer].output[0]

        if final_node_name is None:
            raise ValueError(
                f"Node at index {emb_extraction_layer} does not have a name set"
            )

    truncate_onnx_model(
        onnx_filepath=model_path,
        output_filepath=output_filepath,
        final_node_names=[final_node_name],
        graph_output_names=[graph_output_name],
        graph_output_shapes=None,
    )

    return output_filepath, tmp_file
