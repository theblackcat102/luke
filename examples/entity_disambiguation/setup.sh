

# 0. Setup dump
python -m luke.cli build-dump-db enwiki-latest-pages-articles.xml.bz2 ./enwiki_latest

# 1. setup pretrain datasets 
python -m luke.cli build-wikipedia-pretraining-dataset \
    ./enwiki_20210320.db \
    roberta-base \
    ./enwiki_20210320-ent-vocab.jsonl \
    ./enwiki_20210320_pretrain_dataset \
    --max-seq-length 300

# 2. start pretrain

# build mention database
python -m luke.cli build-entity-vocab  \
    ./enwiki_20210320.db ./enwiki_20210320-ent-vocab.jsonl \
    --vocab-size 280000


# 3. setup mention database
python -m examples.cli mention-db build-from-wikipedia \
    ./enwiki_20210320.db \
    ./enwiki_20210320_mention.db \
    --min-link-count 5 \
    --max-candidate-size 100 \
    --min-link-prob 0.1

# 4. setup candidate lists
python -m examples.cli entity-linking create-candidate-list  \
    data/entity-disambiguation/enwiki_20210320/enwiki_20210320.db \
    data/entity-disambiguation/enwiki_20210320/enwiki_20210320_mention.db \
    data/entity-disambiguation/enwiki_20210320/candidate.titles \
    --data-dir data/entity-disambiguation/datasets

# 5. setup title list
python -m examples.cli entity-linking create-title-list  \
    data/entity-disambiguation/enwiki_20210320/enwiki_20210320.db \
    data/entity-disambiguation/enwiki_20210320/title.list

# 6. setup redirect tsv
python -m examples.cli entity-linking create-redirect-tsv  \
    data/entity-disambiguation/enwiki_20210320/enwiki_20210320.db \
    data/entity-disambiguation/enwiki_20210320/redirect.tsv

# 7. create cached datasets and titles
python -m examples.cli entity-linking cache-datasets-and-titles  \
    --data-dir data/entity-disambiguation/datasets \
    --mentiondb-file data/entity-disambiguation/enwiki_20210320/enwiki_20210320_mention.db \
    --titles-file data/entity-disambiguation/enwiki_20210320/title.list \
    --redirects-file data/entity-disambiguation/enwiki_20210320/redirect.tsv



# 8. test run
python -m examples.cli  \
    --model-file luke-roberta-base-enwiki_20210320/model_step300000.bin \
    --output-dir luke-roberta-base-enwiki_20210320/entity_disambiguation/step300k/ \
    entity-linking run \
    --no-train \
    --train-batch-size 8 \
    --fix-entity-emb \
    --fix-entity-bias \
    --max-seq-length 512 \
    --num-train-epochs 30 \
    --do-eval \
    --cached-dataset data/entity-disambiguation/enwiki_20210320/cached_datasets.pkl \
    --cached-titles data/entity-disambiguation/enwiki_20210320/cached_titles.pkl \
    --data-dir data/entity-disambiguation/test_generated/ \
    --mentiondb-file data/entity-disambiguation/enwiki_20210320/enwiki_20210320_mention.db \
    --titles-file data/entity-disambiguation/enwiki_20210320/title.list \
    --redirects-file data/entity-disambiguation/enwiki_20210320/enwiki_20210320_redirect.tsv

mkdir luke-roberta-base-enwiki_20210320/entity_disambiguation/step300k/tune

python -m examples.cli  \
    --model-file luke-roberta-base-enwiki_20210320/model_step300000.bin \
    --output-dir luke-roberta-base-enwiki_20210320/entity_disambiguation/step300k/tune \
    entity-linking run \
    --do-train \
    --train-batch-size 16 \
    --fix-entity-emb \
    --fix-entity-bias \
    --max-seq-length 512 \
    --num-train-epochs 30 \
    --do-eval \
    --cached-dataset data/entity-disambiguation/enwiki_20210320/cached_datasets.pkl \
    --cached-titles data/entity-disambiguation/enwiki_20210320/cached_titles.pkl \
    --data-dir data/entity-disambiguation/test_generated/ \
    --mentiondb-file data/entity-disambiguation/enwiki_20210320/enwiki_20210320_mention.db \
    --titles-file data/entity-disambiguation/enwiki_20210320/title.list \
    --redirects-file data/entity-disambiguation/enwiki_20210320/enwiki_20210320_redirect.tsv
# python -m luke.cli build-entity-vocab  \./enwiki_20210320.db \
#  ./output_ent-vocab.jsonl \



# python -m luke.cli pretrain     \
#     ./enwiki_20210320_pretrain_dataset \
#     luke-roberta-base-enwiki_20210320    \
#     --bert-model-name roberta-base   \
#     --entity-emb-size 256  \
#     --learning-rate 5e-5 \
#     --warmup-steps 5000 \
#     --batch-size 112      \
#     --gradient-accumulation-steps 1    \
#     --local-rank -1    \
#     --parallel     \
#     --log-dir logs/luke-roberta-base-enwiki_20210320 \
#     --save-interval-steps 50000