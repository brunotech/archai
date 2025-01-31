# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from typing import List, Tuple, Union, Optional
import os

from overrides import overrides, EnforceOverrides
from torch.utils.data.dataset import Dataset

import torchvision
from torchvision.transforms import transforms

from archai.datasets.dataset_provider import DatasetProvider, ImgSize, register_dataset_provider, TrainTestDatasets
from archai.common.config import Config
from archai.common import utils


class AircraftProvider(DatasetProvider):
    def __init__(self, conf_dataset:Config):
        super().__init__(conf_dataset)
        self._dataroot = utils.full_path(conf_dataset['dataroot'])

    @overrides
    def get_datasets(self, load_train:bool, load_test:bool,
                     transform_train, transform_test)->TrainTestDatasets:
        trainset, testset = None, None

        if load_train:
            trainpath = os.path.join(self._dataroot, 'aircraft', 'train')            
            trainset = torchvision.datasets.ImageFolder(trainpath, transform=transform_train)
        if load_test:
            testpath = os.path.join(self._dataroot, 'aircraft', 'test')
            testset = torchvision.datasets.ImageFolder(testpath, transform=transform_test)

        return trainset, testset

    @overrides
    def get_transforms(self, img_size:ImgSize)->tuple:

        if isinstance(img_size, int):
            img_size = (img_size, img_size)
        
        # TODO: update MEAN, STD, currently mit67 values
        MEAN = [0.4893, 0.4270, 0.3625]
        STD = [0.2631, 0.2565, 0.2582]

        # transformations match that in
        # https://github.com/antoyang/NAS-Benchmark/blob/master/DARTS/preproc.py
        train_transf = [
            transforms.RandomResizedCrop(img_size, scale=(0.75, 1)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(
                brightness=0.4,
                contrast=0.4,
                saturation=0.4,
                hue=0.2)
        ]

        margin_size = (int(img_size[0] + img_size[0]*0.1), int(img_size[1] + img_size[1]*0.1))
        test_transf = [transforms.Resize(margin_size), transforms.CenterCrop(img_size)]
        #test_transf = [transforms.Resize(img_size)]

        normalize = [
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD)
        ]

        train_transform = transforms.Compose(train_transf + normalize)
        test_transform = transforms.Compose(test_transf + normalize)

        return train_transform, test_transform

register_dataset_provider('aircraft', AircraftProvider)