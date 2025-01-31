# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from archai.common.config import Config
from archai.datasets import data
from torchvision import transforms
from archai.common.ml_utils import channel_norm

if __name__ == '__main__':
    conf = Config(config_filepath='benchmarks/confs/datasets/flower102.yaml')

    conf_dataset = conf['dataset']

    ds_provider = data.create_dataset_provider(conf_dataset)

    train_ds, _ = ds_provider.get_datasets(True, False,
        transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor()]),
        transforms.Compose([]))

    print(channel_norm(train_ds))

    exit(0)