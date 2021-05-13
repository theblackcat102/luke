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
import json
from wikipedia2vec.dump_db import DumpDB
from torch.utils.tensorboard import SummaryWriter
from luke.utils.entity_vocab import MASK_TOKEN, PAD_TOKEN, UNK_TOKEN

from ..utils.trainer import Trainer, trainer_args
from .model import LukeForEntityDisambiguation

# import added
from examples.utils.mention_db import MentionDB, BertLowercaseNormalizer
from transformers.tokenization_bert import BasicTokenizer
from .utils import EntityDisambiguationDataset, convert_documents_to_features

logger = logging.getLogger(__name__)

@click.group(name='entity-linking')
def cli():
    pass


@cli.command()
@click.option('--cached-dataset', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/generated/test_train_data/cached_datasets.pkl')
@click.option('--cached-titles', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/generated/test_train_data/cached_titles.pkl')
@click.option('--data-dir', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/generated/test_train_data')
@click.option('--mentiondb-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/mention_db_from_p_e_m_v2')
@click.option('--titles-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/enwiki_20181220_titles.txt')
@click.option('--redirects-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/enwiki_20181220_redirects.tsv')
@click.option('-t', '--test-set', default=['clueweb','test_a', 'test_b', 'ace2004', 'aquaint', 'msnbc', 'wikipedia'],
              multiple=True)
@click.option('--do-train/--no-train', default=True)
@click.option('--log-dir',  default='luke')
@click.option('--do-eval/--no-eval', default=True)
@click.option('--num-train-epochs', default=10)
@click.option('--train-batch-size', default=1) # * acm_step =  4 8 16 32 64 
@click.option('--max-seq-length', default=128) # 512
@click.option('--max-candidate-length', default=20)
@click.option('--max-entity-length', default=32)
@click.option('--masked-entity-prob', default=0.9) # default 0.9
@click.option('--candidate-generation/--no-candidate-generation', default=True)
@click.option('--use-context-entities/--no-context-entities', default=False)
@click.option('--context-entity-selection-order', default='highest_prob',
              type=click.Choice(['natural', 'random', 'highest_prob']))
@click.option('--document-split-mode', default='simple', type=click.Choice(['simple', 'per_mention'])) # 使わん
@click.option('--fix-entity-emb/--update-entity-emb', default=True)
@click.option('--fix-entity-bias/--update-entity-bias', default=True)
@click.option('--seed', default=1) # set_seed
@trainer_args
@click.pass_obj
def run(common_args, **task_args):
    task_args.update(common_args)
    args = Namespace(**task_args)

    logger.info('Set Seed')
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    logger.info('Loading Cached Datasets')
    with open(args.cached_dataset, 'rb') as f:
        dataset = pickle.load(f)

    logger.info('Loading Cached Titles')
    with open(args.cached_titles, 'rb') as f:
        entity_titles = pickle.load(f)
    
    logger.info('Building Entity Vocab')

    if os.path.exists('temp_new_entity.json'):
        with open('temp_new_entity.json', 'r') as f:
            entity_vocab = json.load(f)
    else:
        entity_vocab = {PAD_TOKEN: 0, MASK_TOKEN: 2, UNK_TOKEN: 1}
        orig_entity_vocab = args.entity_vocab
        not_found_titles = ['[NO_E]']
        id2entity = {}
        used_index = list(range(274478))

        not_used_entity = {}

        for n, title in enumerate(sorted(entity_titles), 2): # [NO_E]も入る
            if title in orig_entity_vocab and title not in entity_vocab:
                if orig_entity_vocab[title] in used_index:
                    used_index.remove(orig_entity_vocab[title])
                    max_ent_id = max(max_ent_id, orig_entity_vocab[title])
                    entity_vocab[title] = orig_entity_vocab[title]
                    id2entity[orig_entity_vocab[title]] = title
                else:
                    print(orig_entity_vocab[title], ' index repeated!', title)
                    not_found_titles.append(title)
            else:
                not_found_titles.append(title)


        for idx in range(max_ent_id):
            if idx not in id2entity:
                ent_text = not_found_titles.pop()
                entity_vocab[ent_text] = idx
                id2entity[idx] = ent_text

            if len(not_found_titles)== 0:
                break

        assert '[NO_E]' in entity_titles
        
        print(len(orig_entity_vocab), len(entity_vocab), max_ent_id)
        with open('temp_new_entity.json', 'w') as f:
            json.dump(entity_vocab, f)



    max_ent_id = max([ idx for _, idx in entity_vocab.items() ])
    model_config = args.model_config
    model_config.entity_vocab_size = max_ent_id+1 # これを orig_emb[title] or orig_emb[UNK] or new_ones
    logger.info('Model configuration: %s', model_config)
    model_weights = args.model_weights
    orig_entity_emb = model_weights['entity_embeddings.entity_embeddings.weight'] # 事前学習済みのエンティティ埋め込み (Ve ~= 1M)
    vocab_size = orig_entity_emb.shape[0]
    print(vocab_size)
    orig_entity_vocab = args.entity_vocab
    orig_entity_emb = model_weights['entity_embeddings.entity_embeddings.weight']

    if orig_entity_emb.size(0) != len(entity_vocab):  # detect whether the model is the fine-tuned one
        logger.info("Entity embedding remapped!")
        entity_emb = orig_entity_emb.new_zeros((max_ent_id+1, 300))
        for title, index in entity_vocab.items():
            if title in orig_entity_vocab and title != '[NO_E]':
                orig_index = orig_entity_vocab[title]
                entity_emb[index] = orig_entity_emb[orig_index]
        model_weights['entity_embeddings.entity_embeddings.weight'] = entity_emb
        model_weights['entity_embeddings.mask_embedding'] = entity_emb[1].view(1, -1)
        model_weights['entity_predictions.decoder.weight'] = entity_emb
        del entity_emb
    del orig_entity_emb


    logger.info('Building Model')
    model = LukeForEntityDisambiguation(model_config)
    model.load_state_dict(model_weights, strict=False)


    logger.info('Being on device')
    model.to(args.device)

    def collate_fn(batch, is_eval=False):
        def create_padded_sequence(attr_name, padding_value):
            tensors = [torch.tensor(getattr(o, attr_name), dtype=torch.long) for o in batch]
            return torch.nn.utils.rnn.pad_sequence(tensors, batch_first=True, padding_value=padding_value)

        ret = dict(
            word_ids=create_padded_sequence('word_ids', args.tokenizer.pad_token_id),
            word_segment_ids=create_padded_sequence('word_segment_ids', 0),
            word_attention_mask=create_padded_sequence('word_attention_mask', 0),
            entity_ids=create_padded_sequence('entity_ids', 0),
            entity_position_ids=create_padded_sequence('entity_position_ids', -1),
            entity_segment_ids=create_padded_sequence('entity_segment_ids', 0),
            entity_attention_mask=create_padded_sequence('entity_attention_mask', 0),
        )
        ret['entity_candidate_ids'] = create_padded_sequence('entity_candidate_ids', 0)

        if is_eval:
            ret['document'] = [o.document for o in batch]
            ret['mentions'] = [o.mentions for o in batch]
            ret['target_mention_indices'] = [o.target_mention_indices for o in batch] # instanceにK個mentionがあれば，[range(K)]となる 

        return ret

    # train -> test_b
    if args.do_train:

        if args.output_dir:
            output_eval_file = os.path.join(args.output_dir, 'init_eval_results.txt')
            if not os.path.exists(output_eval_file):
                model.eval()
                results = {}
                for dataset_name in args.test_set:
                    logger.info('***** Evaluating: %s *****', dataset_name)
                    eval_documents = getattr(dataset, dataset_name)
                    eval_data = convert_documents_to_features(
                        eval_documents, args.tokenizer, entity_vocab, 'eval', 
                        150 if 'clueweb'==dataset_name else args.max_seq_length,
                        max_candidate_length=20 if 'clueweb'==dataset_name else  args.max_candidate_length,
                        max_mention_length=20  if 'clueweb'==dataset_name else args.max_mention_length,
                        max_entity_length=20 if 'clueweb'==dataset_name else args.max_entity_length)
                    eval_dataloader = DataLoader(eval_data, batch_size=1,
                                                collate_fn=functools.partial(collate_fn, is_eval=True))
                    predictions_file = None
                    if args.output_dir:
                        predictions_file = os.path.join(args.output_dir, 'eval_predictions_%s.jsonl' % dataset_name)
                    results[dataset_name] = evaluate(args, eval_dataloader, model, entity_vocab, predictions_file)

                if args.output_dir:
                    output_eval_file = os.path.join(args.output_dir, 'init_eval_results.txt')
                    with open(output_eval_file, 'w') as f:
                        json.dump(results, f, indent=2, sort_keys=True)
                model.train()

        summary_writer = SummaryWriter(args.log_dir)

        logger.info('*****Training*****')
        logger.info('Converting Documents to Features')
        train_data = convert_documents_to_features(
            dataset.train, args.tokenizer, entity_vocab, 'train', args.max_seq_length,
            args.max_candidate_length, args.max_mention_length, args.max_entity_length)
        train_dataloader = DataLoader(train_data, batch_size=args.train_batch_size, collate_fn=collate_fn, shuffle=True)
        logger.info('Fix entity embeddings during training: %s', args.fix_entity_emb)
        if args.fix_entity_emb:
            model.entity_embeddings.entity_embeddings.weight.requires_grad = False
        logger.info('Fix entity bias during training: %s', args.fix_entity_bias)
        num_train_steps = len(train_dataloader) // args.gradient_accumulation_steps * args.num_train_epochs

        logger.info("Trainable weights {:.3f}M".format(sum(p.numel() for p in model.parameters() if p.requires_grad)/ 1e6))
        logger.info("Total weights {:.3f}M".format( sum(p.numel() for p in model.parameters() ) / 1e6))

        trainer = EntityLinkingTrainer(args, model, train_dataloader, num_train_steps, writer=summary_writer)
        trainer.train()
            
    results = {}
    torch.cuda.empty_cache()

    if args.do_eval:
        model.eval()

        for dataset_name in args.test_set:
            logger.info('***** Evaluating: %s *****', dataset_name)
            eval_documents = getattr(dataset, dataset_name)
            eval_data = convert_documents_to_features(
                eval_documents, args.tokenizer, entity_vocab, 'eval', 
                200 if 'clueweb'==dataset_name else args.max_seq_length,
                max_candidate_length=20 if 'clueweb'==dataset_name else  args.max_candidate_length,
                max_mention_length=20  if 'clueweb'==dataset_name else args.max_mention_length,
                max_entity_length=20 if 'clueweb'==dataset_name else args.max_entity_length)

            eval_dataloader = DataLoader(eval_data, batch_size=1,
                                         collate_fn=functools.partial(collate_fn, is_eval=True))
            predictions_file = None
            if args.output_dir:
                predictions_file = os.path.join(args.output_dir, 'eval_predictions_%s.jsonl' % dataset_name)
            results[dataset_name] = evaluate(args, eval_dataloader, model, entity_vocab, predictions_file)

        if args.output_dir:
            output_eval_file = os.path.join(args.output_dir, 'eval_results.txt')
            with open(output_eval_file, 'w') as f:
                json.dump(results, f, indent=2, sort_keys=True)

    return results



@cli.command()
@click.option('--data-dir', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/generated/test_train_data')
@click.option('--mentiondb-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/mention_db_from_p_e_m_v2')
@click.option('--titles-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/enwiki_20181220_titles.txt')
@click.option('--redirects-file', type=click.Path(exists=True), default='/mnt/usbdisk1/entity_linking/data-3/enwiki_20181220_redirects.tsv')
def cache_datasets_and_titles(data_dir, mentiondb_file, titles_file, redirects_file):
    logger.info('Building Datasets')
    dataset = EntityDisambiguationDataset(data_dir, mentiondb_file, titles_file, redirects_file)
    logger.info('Pickling Datasets')

    logger.info('--Pickled')
    logger.info(cache_file)
    logger.info('Building Entity Titles')
    entity_titles = []
    for data in dataset.get_all_datasets():
        for document in data:
            for mention in document.mentions:
                entity_titles.append(mention.title)
                for candidate in mention.candidates:
                    entity_titles.append(candidate.title)
    logger.info('Frozing Titles (Time Consuming...)')
    entity_titles = frozenset(entity_titles)
    logger.info('Pickling Entity Titles')
    cache_file = os.path.join(
        data_dir,
        "cached_titles.pkl",
    )
    with open(cache_file, 'wb') as f:
        pickle.dump(entity_titles, f)
    logger.info('--Pickled')
    logger.info(cache_file)
    logger.info('DONE')




@cli.command()
@click.argument('dump_db_file', type=click.Path(exists=True))
@click.argument('mention_db_file', type=click.Path(exists=True))
@click.argument('out_file', type=click.File('w'))
@click.option('--data-dir', type=click.Path(exists=True), default='data/entity-disambiguation')
def create_candidate_list(dump_db_file, mention_db_file, out_file, data_dir):
    dump_db = DumpDB(dump_db_file)
    titles = set()
    valid_titles = frozenset(dump_db.titles())

    reader = EntityDisambiguationDataset(data_dir, mention_db_file)
    for documents in tqdm(reader.get_all_datasets()):
        for document in tqdm(documents):
            for mention in document.mentions:
                candidates = mention.candidates
                for candidate in candidates:
                    title = dump_db.resolve_redirect(candidate.title)
                    if title in valid_titles:
                        titles.add(title)

    for title in titles:
        out_file.write(title + '\n')

@cli.command()
@click.argument('dump_db_file', type=click.Path(exists=True))
@click.argument('out_file', type=click.File(mode='w'))
def create_title_list(dump_db_file, out_file):
    dump_db = DumpDB(dump_db_file)

    for title in dump_db.titles():
        out_file.write(f'{title}\n')


@cli.command()
@click.argument('dump_db_file', type=click.Path(exists=True))
@click.argument('out_file', type=click.File(mode='w'))
def create_redirect_tsv(dump_db_file, out_file):
    dump_db = DumpDB(dump_db_file)

    for src, dest in dump_db.redirects():
        out_file.write(f'{src}\t{dest}\n')


class EntityLinkingTrainer(Trainer):
    def _create_model_arguments(self, batch):
        batch['entity_labels'] = batch['entity_ids'].clone()
        for index, entity_length in enumerate(batch['entity_attention_mask'].sum(1).tolist()):
            masked_entity_length = max(1, round(entity_length * self.args.masked_entity_prob))
            permutated_indices = torch.randperm(entity_length)[:masked_entity_length]
            batch['entity_ids'][index, permutated_indices[:masked_entity_length]] = 1  # [MASK]
            batch['entity_labels'][index, permutated_indices[masked_entity_length:]] = -1

        return batch


def evaluate(args, eval_dataloader, model, entity_vocab, output_file=None):
    predictions = []
    context_entities = [] # 
    labels = []
    documents = []
    mentions = []
    reverse_entity_vocab = {v: k for k, v in entity_vocab.items()}
    for item in tqdm(eval_dataloader, leave=True):  # the batch size must be 1
        inputs = {k: v.to(args.device)
                  for k, v in item.items() if k not in ('document', 'mentions', 'target_mention_indices')}
        entity_ids = inputs.pop('entity_ids')
        entity_attention_mask = inputs.pop('entity_attention_mask')
        input_entity_ids = entity_ids.new_full(entity_ids.size(), 1)  # [MASK]
        entity_length = entity_ids.size(1)
        assert inputs['entity_position_ids'].max() < 512
        with torch.no_grad():
            logits = model(entity_ids=input_entity_ids, entity_attention_mask=entity_attention_mask, **inputs)[0]
            result = torch.argmax(logits, dim=2).squeeze(0)

        for index in item['target_mention_indices'][0]:
            predictions.append(result[index].item())
            labels.append(entity_ids[0, index].item())
            documents.append(item['document'][0])
            mentions.append(item['mentions'][0][index])
            context_entities.append([])

    num_correct = 0
    num_mentions = 0
    num_mentions_with_candidates = 0

    num_gold = 0
    num_pred = 0

    eval_predictions = []
    for prediction, label, document, mention, cxt in zip(predictions, labels, documents, mentions, context_entities):

        assert not (mention.candidates and prediction == 0)
        assert label != 0

        if reverse_entity_vocab[label] != '[NO_E]':
            num_gold += 1

        if reverse_entity_vocab[label] != '[NO_E]' and prediction == label:
            num_correct += 1

        if reverse_entity_vocab[prediction] != '[NO_E]':
            num_pred += 1

        num_mentions += 1
        
        #if mention.candidates:
            # num_mentions_with_candidates += 1

        eval_predictions.append(dict(
            document_id=document.id,
            document_words=document.words,
            document_length=len(document.words),
            mention_length=len(document.mentions),
            mention=dict(label=mention.title,
                            text=mention.text,
                            span=(mention.start, mention.end),
                            candidate_length=len(mention.candidates),
                            candidates=[dict(prior_prob=c.prior_prob, title=c.title) for c in mention.candidates]),
            prediction=reverse_entity_vocab[prediction],
            context_entities=cxt
        ))

    if output_file:
        with open(output_file, 'w') as f:
            for obj in eval_predictions:
                f.write(json.dumps(obj) + '\n')

    precision = num_correct / num_pred
    recall = num_correct / num_gold
    f1 = 2.0 * precision * recall / (precision + recall)

    logger.info('f1: %.5f', f1)
    logger.info('precision: %.5f', precision)
    logger.info('recall: %.5f', recall)
    logger.info('#mentions: %d', num_mentions)
    logger.info('#gold mentions: %d', num_gold)
    logger.info('#prediction as entity: %d', num_pred)
    logger.info('#correct: %d', num_correct)

    return dict(precision=precision, recall=recall, f1=f1)