# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from typing import Iterator, Mapping, Type, Optional, Tuple, List
import math
import copy
import random
import os

from overrides import EnforceOverrides

from torch.utils.data.dataloader import DataLoader

from archai.common.common import logger

from archai.common.config import Config
from archai.nas.model_desc_builder import ModelDescBuilder
from archai.nas.arch_trainer import TArchTrainer
from archai.common.trainer import Trainer
from archai.nas.model_desc import CellType, ModelDesc
from archai.datasets import data
from archai.nas.model import Model
from archai.common.metrics import EpochMetrics, Metrics
from archai.common import utils
from archai.nas.finalizers import Finalizers


class ModelMetrics:
    def __init__(self, model:Model, metrics:Metrics) -> None:
        self.model = model
        self.metrics = metrics

class SearchResult:
    def __init__(self, model_desc:Optional[ModelDesc],
                 search_metrics:Optional[Metrics],
                 train_metrics:Optional[Metrics]) -> None:
        self.model_desc = model_desc
        self.search_metrics = search_metrics
        self.train_metrics = train_metrics

class Searcher(EnforceOverrides):
    def search(self, conf_search:Config, model_desc_builder:ModelDescBuilder,
                 trainer_class:TArchTrainer, finalizers:Finalizers)->SearchResult:

        # region config vars
        conf_model_desc = conf_search['model_desc']
        conf_post_train = conf_search['post_train']

        cells = conf_model_desc['n_cells']
        reductions = conf_model_desc['n_reductions']
        nodes = conf_model_desc['n_nodes']
        # endregion

        # build model description that we will search on
        model_desc = self.build_model_desc(model_desc_builder, conf_model_desc,
                                           reductions, cells, nodes)

        # perform search on model description
        model_desc, search_metrics = self.search_model_desc(conf_search, model_desc,
                                                     trainer_class, finalizers)

        # train searched model for few epochs to get some perf metrics
        model_metrics = self.train_model_desc(model_desc, conf_post_train)

        search_result = SearchResult(model_desc, search_metrics, model_metrics.metrics)
        self.clean_log_result(conf_search, search_result)

        return search_result

    def clean_log_result(self, conf_search:Config, search_result:SearchResult)->None:
        final_desc_filename = conf_search['final_desc_filename']

        # remove weights info deom model_desc so its more readable
        search_result.model_desc.clear_trainables()
        # if file name was specified then save the model desc
        if final_desc_filename:
            search_result.model_desc.save(final_desc_filename)
        if search_result.search_metrics is not None:
            logger.info({'search_top1_val':
                search_result.search_metrics.best_val_top1()})
        if search_result.train_metrics is not None:
            logger.info({'train_top1_val':
                search_result.train_metrics.best_val_top1()})

    def build_model_desc(self, model_desc_builder:ModelDescBuilder,
                         conf_model_desc:Config,
                         reductions:int, cells:int, nodes:int)->ModelDesc:
        # reset macro params in copy of config
        conf_model_desc = copy.deepcopy(conf_model_desc)
        conf_model_desc['n_reductions'] = reductions
        conf_model_desc['n_cells'] = cells

        # create model desc for search using model config
        # we will build model without call to model_desc_builder for pre-training
        model_desc = model_desc_builder.build(conf_model_desc, template=None)

        return model_desc

    def get_data(self, conf_loader:Config)->Tuple[Optional[DataLoader], Optional[DataLoader]]:

        # this dict caches the dataset objects per dataset config so we don't have to reload
        # the reason we do dynamic attribute is so that any dependent methods
        # can do ray.remote
        if not hasattr(self, '_data_cache'):
            self._data_cache = {}

        # first get from cache
        train_ds, val_ds = self._data_cache.get(id(conf_loader), (None, None))
        # if not found in cache then create
        if train_ds is None:
            train_ds, val_ds, _ = data.get_data(conf_loader)
            self._data_cache[id(conf_loader)] = (train_ds, val_ds)
        return train_ds, val_ds

    def finalize_model(self, model:Model, finalizers:Finalizers)->ModelDesc:
        return finalizers.finalize_model(model, restore_device=False)

    def search_model_desc(self, conf_search:Config, model_desc:ModelDesc,
                          trainer_class:TArchTrainer, finalizers:Finalizers)\
                              ->Tuple[ModelDesc, Metrics]:

        logger.pushd('arch_search')

        conf_train = conf_search['trainer']
        conf_loader = conf_train['loader']

        model = Model(model_desc, droppath=False, affine=False)

        # get data
        train_dl, val_dl = self.get_data(conf_loader)
        assert train_dl is not None

        # search arch
        arch_trainer = trainer_class(conf_train, model, checkpoint=None)
        search_metrics = arch_trainer.fit(train_dl, val_dl)

        # finalize
        found_desc = self.finalize_model(model, finalizers)

        logger.popd()

        return found_desc, search_metrics

    def train_model_desc(self, model_desc:ModelDesc, conf_train:Config)\
            ->Optional[ModelMetrics]:
        """Train given description"""

        # region conf vars
        conf_trainer = conf_train['trainer']
        conf_loader = conf_train['loader']
        trainer_title = conf_trainer['title']
        epochs = conf_trainer['epochs']
        drop_path_prob = conf_trainer['drop_path_prob']
        # endregion

        # if epochs ==0 then nothing to train, so save time
        if  epochs <= 0:
            return None

        logger.pushd(trainer_title)

        model = Model(model_desc, droppath=drop_path_prob>0.0, affine=True)

        # get data
        train_dl, val_dl = self.get_data(conf_loader)
        assert train_dl is not None

        trainer = Trainer(conf_trainer, model, checkpoint=None)
        train_metrics = trainer.fit(train_dl, val_dl)

        logger.popd()

        return ModelMetrics(model, train_metrics)
