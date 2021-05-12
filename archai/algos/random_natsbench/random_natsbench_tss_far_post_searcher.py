import math as ma
from time import time
from typing import Set
import os
import random
from copy import deepcopy

from overrides import overrides

from archai.nas.searcher import Searcher, SearchResult
from archai.common.config import Config
from archai.common.common import logger
from archai.nas.model_desc_builder import ModelDescBuilder
from archai.nas.arch_trainer import TArchTrainer
from archai.common.trainer import Trainer
from archai.nas.model_desc import CellType, ModelDesc
from archai.datasets import data
from archai.nas.model import Model
from archai.common.metrics import EpochMetrics, Metrics
from archai.common import utils
from archai.nas.finalizers import Finalizers
from archai.algos.proxynas.conditional_trainer import ConditionalTrainer
from archai.algos.proxynas.freeze_trainer import FreezeTrainer
from archai.algos.natsbench.natsbench_utils import create_natsbench_tss_api, model_from_natsbench_tss

class RandomNatsbenchTssFarPostSearcher(Searcher):

    @overrides
    def search(self, conf_search:Config)->SearchResult:

        # region config vars
        max_num_models = conf_search['max_num_models']
        ratio_fastest_duration = conf_search['ratio_fastest_duration']
        dataroot = utils.full_path(conf_search['loader']['dataset']['dataroot'])
        dataset_name = conf_search['loader']['dataset']['name']
        natsbench_location = os.path.join(dataroot, 'natsbench', conf_search['natsbench']['natsbench_tss_fast'])
        conf_train = conf_search['trainer']
        conf_loader = conf_search['loader']
        conf_train_freeze = conf_search['freeze_trainer']
        conf_train_post = conf_search['post_trainer']
        # endregion

        # create the natsbench api
        api = create_natsbench_tss_api(natsbench_location)

        # presample max number of archids without replacement
        random_archids = random.sample(range(len(api)), k=max_num_models)

        best_trains = [(-1, -ma.inf)]
        best_tests = [(-1, -ma.inf)]
        fastest_cond_train = ma.inf
        
        for archid in random_archids:
            # get model
            model = model_from_natsbench_tss(archid, dataset_name, api)

            # NOTE: we don't pass checkpoint to the trainers
            # as it creates complications and we don't need it
            # as these trainers are quite fast
            checkpoint = None

            # if during conditional training it
            # starts exceeding fastest time to
            # reach threshold by a ratio then early
            # terminate it
            logger.pushd(f'conditional_training_{archid}')
            
            data_loaders = self.get_data(conf_loader)
            time_allowed = ratio_fastest_duration * fastest_cond_train
            cond_trainer = ConditionalTrainer(conf_train, model, checkpoint, time_allowed) 
            cond_trainer_metrics = cond_trainer.fit(data_loaders)
            cond_train_time = cond_trainer_metrics.total_training_time()

            if cond_train_time >= time_allowed:
                # this arch exceeded time to reach threshold
                # cut losses and move to next one
                logger.info(f'{archid} exceeded time allowed. Terminating and ignoring.')
                logger.popd()
                continue

            if cond_train_time < fastest_cond_train:
                fastest_cond_train = cond_train_time
                logger.info(f'fastest condition train till now: {fastest_cond_train} seconds!')
            logger.popd()

            # if we did not early terminate in conditional 
            # training then freeze train
            # get data with new batch size for freeze training
            # NOTE: important to create copy and modify as otherwise get_data will return
            # a cached data loader by hashing the id of conf_loader
            conf_loader_freeze = deepcopy(conf_loader)
            conf_loader_freeze['train_batch'] = conf_loader['freeze_loader']['train_batch'] 

            logger.pushd(f'freeze_training_{archid}')
            data_loaders = self.get_data(conf_loader_freeze)
            # now just finetune the last few layers
            checkpoint = None
            trainer = FreezeTrainer(conf_train_freeze, model, checkpoint)
            freeze_train_metrics = trainer.fit(data_loaders)
            logger.popd()

            this_arch_top1 = freeze_train_metrics.best_train_top1()    
            if this_arch_top1 > best_trains[-1][1]:
                best_trains.append((archid, this_arch_top1))

                # get the full evaluation result from natsbench
                info = api.get_more_info(archid, dataset_name, hp=200, is_random=False)
                this_arch_top1_test = info['test-accuracy']
                best_tests.append((archid, this_arch_top1_test))

            # dump important things to log
            logger.pushd(f'best_trains_tests_{archid}')
            logger.info({'best_trains':best_trains, 'best_tests':best_tests})
            logger.popd()

            post_best_tests = self._post_train_top(best_trains, dataset_name, api, conf_loader, conf_train_post)
            logger.pushd(f'post_best_tests')
            logger.info({'post_best_tests':post_best_tests})
            best_test = max(post_best_tests, key=lambda x:x[1])
            logger.info({'best_test_overall':best_test})
            logger.popd()

    def _post_train_top(self, best_trains, dataset_name:str, api, conf_loader, conf_train_post):
        # take the list of best train archs and 
        # choose amongst them
        checkpoint = None
        post_best_trains = [(-1, -ma.inf)]
        post_best_tests = [(-1, -ma.inf)]
        for arch_id, _ in best_trains:
            if arch_id > 0:
                # get model
                model = model_from_natsbench_tss(arch_id, dataset_name, api)

                # regular train              
                logger.pushd(f'post_training_{arch_id}')            
                data_loaders = self.get_data(conf_loader)
                post_trainer = Trainer(conf_train_post, model, checkpoint) 
                post_train_metrics = post_trainer.fit(data_loaders)
                logger.popd()

                this_arch_top1 = post_train_metrics.best_train_top1()    
                if this_arch_top1 > post_best_trains[-1][1]:
                    post_best_trains.append((arch_id, this_arch_top1))
                    # get the full evaluation result from natsbench
                    info = api.get_more_info(arch_id, dataset_name, hp=200, is_random=False)
                    this_arch_top1_test = info['test-accuracy']
                    post_best_tests.append((arch_id, this_arch_top1_test))

        return post_best_tests