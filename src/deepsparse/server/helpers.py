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

from deepsparse import BaseLogger
from deepsparse.loggers.build_logger import _get_target_identifier, build_logger
from deepsparse.server.config import ServerConfig


__all__ = ["server_logger_from_config"]


def server_logger_from_config(config: ServerConfig) -> BaseLogger:
    data_logging = {}
    for endpoint in config.endpoints:
        if endpoint.data_logging is None:
            continue
        for target, metric_functions in endpoint.data_logging.copy().items():
            new_target = _get_target_identifier(
                target_name=target, pipeline_identifier=endpoint.name
            )
            data_logging[new_target] = metric_functions
    return build_logger(
        system_logging_config=config.system_logging,
        loggers_config=config.loggers,
        data_logging_config=data_logging,
    )
