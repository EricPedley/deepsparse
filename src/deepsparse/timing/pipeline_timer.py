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

import time
from typing import Dict, List


__all__ = ["InferenceTimer", "PipelineTimer"]


class InferenceTimer:
    def __init__(self):
        self._staged_start_times = {}
        self._staged_stop_times = {}

    def __repr__(self):
        return f"InferenceTimer({self.times})"

    @property
    def stages(self) -> List[str]:
        return list(self._staged_start_times.keys())

    @property
    def times(self) -> Dict[str, float]:
        return {stage: self.stage_average_time(stage) for stage in self.stages}

    @property
    def all_times(self) -> Dict[str, List[float]]:
        return {stage: self.stage_times(stage) for stage in self.stages}

    def clear(self):
        self._staged_start_times.clear()
        self._staged_stop_times.clear()

    def has_stage(self, stage: str) -> bool:
        return stage in self.stages

    def start(self, stage: str):
        if stage not in self._staged_start_times:
            self._staged_start_times[stage] = []
            self._staged_stop_times[stage] = []

        if len(self._staged_start_times[stage]) != len(self._staged_stop_times[stage]):
            raise ValueError(
                f"Attempting to start {stage} before a previous has been stopped:"
                f" start times len({self._staged_start_times[stage]});"
                f" stop times len({self._staged_stop_times[stage]})"
            )

        self._staged_start_times[stage].append(time.perf_counter())

    def stop(self, stage: str):
        if stage not in self._staged_start_times:
            raise ValueError(
                "Attempting to stop a stage that has not been started: " f"{stage}"
            )

        if (
            len(self._staged_start_times[stage])
            != len(self._staged_stop_times[stage]) + 1
        ):
            raise ValueError(
                f"Attempting to stop {stage} before a previous has been started:"
                f" start times len({self._staged_start_times[stage]});"
                f" stop times len({self._staged_stop_times[stage]})"
            )

        self._staged_stop_times[stage].append(time.perf_counter())

    def stage_times(self, stage: str) -> List[float]:
        if stage not in self._staged_start_times:
            raise ValueError(
                "Attempting to get time deltas for a stage that has not been started: "
                f"{stage}"
            )

        if len(self._staged_start_times[stage]) != len(self._staged_stop_times[stage]):
            raise ValueError(
                "Attempting to get time deltas for a stage that has not been stopped: "
                f"{stage}"
            )

        return [
            self._staged_stop_times[stage][i] - self._staged_start_times[stage][i]
            for i in range(len(self._staged_start_times[stage]))
        ]

    def stage_average_time(self, stage: str) -> float:
        times = self.stage_times(stage)

        return sum(times) / len(times)


class PipelineTimer:
    def __init__(self, enabled: bool = True, multi_inference: bool = False):
        self._multi_inference = multi_inference
        self._enabled = enabled
        self._timers = []

    def __repr__(self):
        return f"PipelineTimer({self.times})"

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value

    @property
    def multi_inference(self):
        return self._multi_inference

    @multi_inference.setter
    def multi_inference(self, value):
        self._multi_inference = value

    @property
    def current_inference(self) -> InferenceTimer:
        return self._timers[-1] if self._timers else None

    @property
    def inferences(self) -> List[InferenceTimer]:
        return self._timers

    @property
    def stages(self) -> List[str]:
        stages = set()

        for timer in self._timers:
            stages.update(timer.stages)

        return list(stages)

    @property
    def times(self) -> Dict[str, float]:
        all_times = self.all_times

        return {
            stage: sum(all_times[stage]) / len(all_times[stage])
            for stage in self.stages
        }

    @property
    def all_times(self) -> Dict[str, List[float]]:
        all_times = {stage: [] for stage in self.stages}

        for timer in self._timers:
            for stage, times in timer.all_times.items():
                all_times[stage].extend(times)

        return all_times

    def reset(self):
        if not self._enabled:
            return

        self._check_start_inference()

        if self.multi_inference:
            self._timers.append(InferenceTimer())
        else:
            self._timers[0].clear()

    def start_inference_stage(self, stage: str):
        if not self._enabled:
            return

        self._check_start_inference()
        self._timers[-1].start(stage)

    def stop_inference_stage(self, stage: str):
        if not self._enabled:
            return

        self._check_start_inference()
        self._timers[-1].stop(stage)

    def _check_start_inference(self):
        if not self.current_inference:
            self._timers.append(InferenceTimer())