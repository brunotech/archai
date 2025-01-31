# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import torch
from archai import cifar10_models
from archai.common.trainer import Trainer
from archai.common.config import Config
from archai.common.common import common_init
from archai.datasets import data

def train_test(conf_eval:Config):
    conf_loader = conf_eval['loader']
    conf_trainer = conf_eval['trainer']

    # create model
    Net = cifar10_models.resnet34
    model = Net().to(torch.device('cuda', 0))

    # get data
    data_loaders = data.get_data(conf_loader)

    # train!
    trainer = Trainer(conf_trainer, model)
    trainer.fit(data_loaders)


if __name__ == '__main__':
    conf = common_init(config_filepath='benchmarks/confs/algos/resnet.yaml;benchmarks/confs/datasets/cifar100.yaml')
    conf_eval = conf['nas']['eval']

    train_test(conf_eval)