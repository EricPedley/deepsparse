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
Usage: validation_script.py [OPTIONS]

  Validation Script for Image Classification Models

Options:
  --dataset-path, --dataset_path DIRECTORY
                                  Path to the validation dataset  [required]
  --model-path, --model_path TEXT
                                  Path/SparseZoo stub for the Image
                                  Classification model to be evaluated.
                                  Defaults to resnet50 trained on
                                  Imagenette  [default: zoo:cv/classification/
                                  resnet_v1-50/pytorch/sparseml/imagenette/
                                  base-none]
  --batch-size, --batch_size INTEGER
                                  Test batch size, must divide the dataset
                                  evenly, else the last batch will be dropped
                                  [default: 1]
  --help                          Show this message and exit.

#########
EXAMPLES
#########

##########
Example command for validating pruned resnet50 on imagenette dataset:
python validation_script.py \
  --dataset-path /path/to/imagenette/

"""
import click
import torchvision
from torchvision import transforms
from tqdm import tqdm

from deepsparse.pipeline import Pipeline
from deepsparse.vision.utils import IMAGENET_RGB_MEANS, IMAGENET_RGB_STDS
from torch.utils.data import DataLoader


resnet50_imagenet_pruned = (
    "zoo:cv/classification/resnet_v1-50/pytorch/sparseml/imagenette/base-none"
)


@click.command()
@click.option(
    "--dataset-path",
    "--dataset_path",
    required=True,
    type=click.Path(dir_okay=True, file_okay=False),
    help="Path to the validation dataset",
)
@click.option(
    "--model-path",
    "--model_path",
    type=str,
    default=resnet50_imagenet_pruned,
    help="Path/SparseZoo stub for the Image Classification model to be "
    "evaluated. Defaults to dense (vanilla) resnet50 trained on Imagenette",
    show_default=True,
)
@click.option(
    "--batch-size",
    "--batch_size",
    type=int,
    default=1,
    show_default=True,
    help="Test batch size, must divide the dataset evenly, else last "
    "batch will be dropped",
)
@click.option(
    "--image-size",
    "--image_size",
    type=int,
    default=224,
    show_default=True,
    help="integer size to evaluate images at (will be reshaped to square shape)",
)
def main(dataset_path: str, model_path: str, batch_size: int, image_size: int):
    """
    Validation Script for Image Classification Models
    """
    non_rand_resize_scale = 256.0 / 224.0  # standard used
    dataset = torchvision.datasets.ImageFolder(
        root=dataset_path,
        transform=transforms.Compose(
            [
                transforms.Resize(round(non_rand_resize_scale * image_size)),
                transforms.CenterCrop(image_size),
                transforms.ToTensor(),
                transforms.Normalize(mean=IMAGENET_RGB_MEANS, std=IMAGENET_RGB_STDS),
            ]
        ),
    )

    data_loader = DataLoader(
        dataset=dataset,
        batch_size=batch_size,
        drop_last=True,
    )

    pipeline = Pipeline.create(
        task="image_classification",
        model_path=model_path,
        batch_size=batch_size,
    )
    correct = total = 0
    progress_bar = tqdm(data_loader)

    for batch in progress_bar:
        batch, actual_labels = batch
        batch = batch.numpy()
        outs = pipeline(images=batch)
        predicted_labels = outs.labels

        for actual, predicted in zip(actual_labels, predicted_labels):
            total += 1
            if isinstance(predicted, str):
                predicted = int(predicted)
            if actual.item() == predicted:
                correct += 1

        if total > 0:
            progress_bar.set_postfix(
                {"Running Accuracy": f"{correct * 100 / total:.2f}%"}
            )

    # prevent division by zero
    if total == 0:
        epsilon = 1e-5
        total += epsilon

    print(f"Accuracy: {correct * 100 / total:.2f} %")


if __name__ == "__main__":
    main()
