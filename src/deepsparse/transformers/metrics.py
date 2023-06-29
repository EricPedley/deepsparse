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

"""
Utilities for evaluation metric computation
"""


from typing import Any, Dict, List, Optional

import numpy
from tqdm import tqdm

import torch
from deepsparse import Pipeline
from deepsparse.transformers.pipelines.text_generation import TextGenerationPipeline
from sklearn.metrics import precision_recall_fscore_support


__all__ = [
    "PrecisionRecallF1",
    "Perplexity",
]


class Perplexity:
    def __init__(self, pipeline: Pipeline, batch_size: int = 16):
        """
        Given the pipeline, compute the perplexity of the model
        on the given text input.

        Code adapted from:
        https://huggingface.co/spaces/evaluate-metric/perplexity/blob/main/perplexity.py # noqa: E501

        :param pipeline: The pipeline to use for text generation
        :param batch_size: The batch size to split the input text into
         non-overlapping batches
        """
        if not isinstance(pipeline, TextGenerationPipeline):
            raise ValueError(
                "Perplexity can only be computed for text generation pipelines"
            )
        self._pipeline = pipeline
        self._batch_size = batch_size
        self._sequence_length = pipeline.sequence_length
        self._loss_fct = torch.nn.CrossEntropyLoss(reduction="none")

        self.perplexities = []

    def add_batch(self, predictions: List[str]):
        """
        Run the model on the given input sequences and compute the perplexity.
        The resulting perplexity is appended to the list of perplexities.

        :param predictions: The predictions to compute perplexity on
        """
        # tokenize the input text
        encodings = self._pipeline.tokenizer(
            predictions,
            return_attention_mask=True,
            max_length=self._sequence_length,
            truncation=True,
            padding="max_length",
        )

        encoded_texts = encodings["input_ids"]
        attention_masks = encodings["attention_mask"]

        # split input_text into non-overlapping batches of `batch_size`
        for start_index in tqdm(range(0, len(encoded_texts), self._batch_size)):
            end_index = min(start_index + self._batch_size, len(encoded_texts))
            encoded_batch = encoded_texts[start_index:end_index]
            attention_mask = attention_masks[start_index:end_index]

            out = self._pipeline(sequences=predictions, return_logits=True)
            logits = out.logits

            labels = encoded_batch

            # shift logits and labels create the input and target for the loss function
            shift_logits = logits[:, :-1, :]
            shift_labels = numpy.stack(labels)[:, 1:]
            shift_attention_mask_batch = numpy.stack(attention_mask)[:, 1:]

            # compute perplexity for this batch
            perplexity_batch = torch.exp(
                (
                    self._loss_fct(
                        torch.tensor(shift_logits.transpose(0, 2, 1)),
                        torch.tensor(shift_labels),
                    )
                    * torch.tensor(shift_attention_mask_batch)
                ).sum(1)
                / torch.tensor(shift_attention_mask_batch).sum(1)
            )
            self.perplexities.extend(perplexity_batch.numpy().tolist())

    def compute(self) -> Dict[str, Any]:
        return {
            "mean_perplexity": numpy.mean(self.perplexities),
            "perplexities": self.perplexities,
        }


class PrecisionRecallF1:
    def __init__(self, id_to_label: Optional[Dict[int, str]] = None):
        self._id_to_label = id_to_label
        self._predictions = None
        self._targets = None

    def add_batch(self, predictions: numpy.ndarray, targets: numpy.ndarray):
        """
        adds a batch of prediction results to track, should be of shape
        (batch_size, num_labels)

        :param predictions: predicted scores from pipeline
        :param targets: target values - label column should be 1 if a label is positive
            0 otherwise
        """
        if predictions.ndim == 1:
            predictions = predictions.reshape(1, predictions.shape[0])
        if targets.ndim == 1:
            targets = targets.reshape(1, targets.shape[0])

        if self._predictions is None:
            self._predictions = predictions
            self._targets = targets
        else:
            self._predictions = numpy.concatenate((self._predictions, predictions))
            self._targets = numpy.concatenate((self._targets, targets))

    def compute(self) -> Dict[str, float]:
        """
        computes per class and macro-averaged precision, recall, and f1 for multiple
        model sample predictions where targets may contain multiple labels

        :return: dictionary of per label and macro-average results for precision,
            recall, and f1
        """
        precision, recall, f1, _ = precision_recall_fscore_support(
            self._targets, self._predictions
        )

        # compile results into required str -> float dict
        results = {}
        for idx in range(self._predictions.shape[1]):
            label = self._id_to_label[idx] if self._id_to_label else str(idx)

            results[f"precision_{label}"] = precision[idx]
            results[f"recall_{label}"] = recall[idx]
            results[f"f1_{label}"] = f1[idx]

        # add macro averages and std to results
        results["precision_macro_average"] = precision.mean()
        results["recall_macro_average"] = recall.mean()
        results["f1_macro_average"] = f1.mean()

        results["precision_std"] = precision.std()
        results["recall_std"] = recall.std()
        results["f1_std"] = f1.std()

        return results
