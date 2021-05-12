import functools
import json
import logging
import os
import random
from argparse import Namespace
import pickle
import numpy as np

import click
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm
from transformers import WEIGHTS_NAME
from wikipedia2vec.dump_db import DumpDB

from luke.utils.entity_vocab import MASK_TOKEN, PAD_TOKEN, UNK_TOKEN

from ..utils.trainer import Trainer, trainer_args
from .model import LukeForEntityDisambiguation

# import added
from examples.utils.mention_db import MentionDB, BertLowercaseNormalizer
from transformers.tokenization_bert import BasicTokenizer
from .utils import EntityDisambiguationDataset, convert_documents_to_features
import argparse


parser = argparse.ArgumentParser(description='Evaluate on confidence order')


