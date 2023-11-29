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


from deepsparse.v2.pipeline import Pipeline
from deepsparse.v2.routers import LinearRouter
from deepsparse.v2.schedulers import ContinuousBatchingScheduler, OperatorScheduler
from tests.deepsparse.v2.middleware.utils import (
    CounterMiddleware,
    OrderTrackerMiddleware,
)
from tests.deepsparse.v2.test_basic_pipeline import (
    AddOneOperator,
    AddTwoOperator,
    IntSchema,
)


def test_pipeline_multiple_runtime_recoded_to_middleware_state():
    """Save recordings in the pipeline level into the middleware state"""
    AddThreePipeline = Pipeline(
        ops=[AddOneOperator(), AddTwoOperator()],
        router=LinearRouter(end_route=2),
        schedulers=[OperatorScheduler()],
        continuous_batching_scheduler=ContinuousBatchingScheduler,
        middleware=[OrderTrackerMiddleware, CounterMiddleware],
    )
    pipeline_input = IntSchema(value=5)
    pipeline_output = AddThreePipeline(pipeline_input)
    assert pipeline_output.value == 8

    expected_middleware_start_order = ["AddOneOperator", "AddTwoOperator"]
    actual_middleware_start_order = AddThreePipeline._middleware._init_middleware[
        0
    ].start_order
    actual_middleware_end_order = AddThreePipeline._middleware._init_middleware[
        0
    ].start_order

    for expected, actual_start, actual_end in zip(
        expected_middleware_start_order,
        actual_middleware_start_order,
        actual_middleware_end_order,
    ):
        assert expected == actual_start
        assert expected == actual_end
