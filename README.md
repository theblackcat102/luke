<img src="resources/luke_logo.png" width="200" alt="LUKE">

[![CircleCI](https://circleci.com/gh/studio-ousia/luke.svg?style=svg&circle-token=49524bfde04659b8b54509f7e0f06ec3cf38f15e)](https://circleci.com/gh/studio-ousia/luke)

---

**LUKE** (**L**anguage **U**nderstanding with **K**nowledge-based
**E**mbeddings) is a new pre-trained contextualized representation of words and
entities based on transformer. It achieves state-of-the-art results on important
NLP benchmarks including
**[SQuAD v1.1](https://rajpurkar.github.io/SQuAD-explorer/)** (extractive
question answering),
**[CoNLL-2003](https://www.clips.uantwerpen.be/conll2003/ner/)** (named entity
recognition), **[ReCoRD](https://sheng-z.github.io/ReCoRD-explorer/)**
(cloze-style question answering),
**[TACRED](https://nlp.stanford.edu/projects/tacred/)** (relation
classification), and
**[Open Entity](https://www.cs.utexas.edu/~eunsol/html_pages/open_entity.html)**
(entity typing).

This repository contains the source code to pre-train the model and fine-tune it
to solve downstream tasks.

## Comparison with State-of-the-Art

LUKE outperforms the previous state-of-the-art methods on five important NLP
tasks:

| Task                           | Dataset                                                                      | Metric | LUKE              | Previous SOTA                                                             |
| ------------------------------ | ---------------------------------------------------------------------------- | ------ | ----------------- | ------------------------------------------------------------------------- |
| Extractive Question Answering  | [SQuAD v1.1](https://rajpurkar.github.io/SQuAD-explorer/)                    | EM/F1  | **90.2**/**95.4** | 89.9/95.1 ([Yang et al., 2019](https://arxiv.org/abs/1906.08237))         |
| Named Entity Recognition       | [CoNLL-2003](https://www.clips.uantwerpen.be/conll2003/ner/)                 | F1     | **94.3**          | 93.5 ([Baevski et al., 2019](https://arxiv.org/abs/1903.07785))           |
| Cloze-style Question Answering | [ReCoRD](https://sheng-z.github.io/ReCoRD-explorer/)                         | EM/F1  | **90.6**/**91.2** | 83.1/83.7 ([Li et al., 2019](https://www.aclweb.org/anthology/D19-6011/)) |
| Relation Classification        | [TACRED](https://nlp.stanford.edu/projects/tacred/)                          | F1     | **72.7**          | 72.0 ([Wang et al. , 2020](https://arxiv.org/abs/2002.01808))             |
| Fine-grained Entity Typing     | [Open Entity](https://www.cs.utexas.edu/~eunsol/html_pages/open_entity.html) | F1     | **78.2**          | 77.6 ([Wang et al. , 2020](https://arxiv.org/abs/2002.01808))             |

These numbers are reported in
[our EMNLP 2020 paper](https://arxiv.org/abs/2010.01057).

## Installation

LUKE can be installed using [Poetry](https://python-poetry.org/):

```bash
poetry install
```

## Released Models

We initially release the pre-trained model with 500K entity vocabulary based on
the `roberta.large` model.

| Name          | Base Model                                                                                          | Entity Vocab Size | Params | Download                                                                                   |
| ------------- | --------------------------------------------------------------------------------------------------- | ----------------- | ------ | ------------------------------------------------------------------------------------------ |
| **LUKE-500K** | [roberta.large](https://github.com/pytorch/fairseq/tree/master/examples/roberta#pre-trained-models) | 500K              | 483 M  | [Link](https://drive.google.com/file/d/1S7smSBELcZWV7-slfrb94BKcSCCoxGfL/view?usp=sharing) |

## Reproducing Experimental Results

The experiments were conducted using Python3.6 and PyTorch 1.2.0 installed on a
server with a single or eight NVidia V100 GPUs. We used
[NVidia's PyTorch Docker container](https://ngc.nvidia.com/catalog/containers/nvidia:pytorch)
19.02. For computational efficiency, we used mixed precision training based on
APEX library which can be installed as follows:

```bash
git clone https://github.com/NVIDIA/apex.git
cd apex
git checkout c3fad1ad120b23055f6630da0b029c8b626db78f
pip install -v --no-cache-dir --global-option="--cpp_ext" --global-option="--cuda_ext" .
```

The commands required to reproduce results are provided as follows.

**Entity Typing on Open Entity Dataset:**

```bash
python -m examples.cli --model-file=luke_large_500k.tar.gz --data-dir=<DATA_DIR> --output-dir=<OUTPUT_DIR> entity-typing run --fp16 --seed=12 --train-batch-size=2 --gradient-accumulation-steps=2 --learning-rate=1e-5 --num-train-epochs=3
```

**Relation Classification on TACRED Dataset:**

```bash
python -m examples.cli --model-file=luke_large_500k.tar --data-dir=<DATA_DIR> --output-dir=experiments/tacred relation-classification run --fp16 --seed=42 --train-batch-size=4 --gradient-accumulation-steps=8 --learning-rate=1e-5 --num-train-epochs=5
```

**Named Entity Recognition on CoNLL-2003 Dataset:**

```bash
python -m examples.cli --model-file=luke_large_500k.tar --data-dir=<DATA_DIR> --output-dir=experiments/ner ner run --fp16 --seed=35 --train-batch-size=2 --gradient-accumulation-steps=2 --learning-rate=1e-5 --num-train-epochs=5
```

**Cloze-style Question Answering on ReCoRD Dataset:**

```bash
python -m examples.cli --model-file=luke_large_500k.tar --num-gpus=8 --data-dir=<DATA_DIR> --output-dir=experiments/record entity-span-qa run --fp16 --seed=4 --train-batch-size=1 --gradient-accumulation-steps=4 --learning-rate=1e-5 --num-train-epochs=2
```

**Extractive Question Answering on SQuAD 1.1 Dataset:**

```bash
python -m examples.cli --num-gpus=8 --model-file=luke_large_500k.tar --data-dir=<DATA_DIR> --output-dir=experiments/squad_v1 reading-comprehension run --no-negative --fp16 --seed=14 --train-batch-size=2 --gradient-accumulation-steps=3 --learning-rate=15e-6 --num-train-epochs=2
```

## Citation

If you use LUKE in your work, please cite the following paper:

```
@inproceedings{yamada2020luke,
  title={LUKE: Deep Contextualized Entity Representations with Entity-aware Self-attention},
  author={Ikuya Yamada and Akari Asai and Hiroyuki Shindo and Hideaki Takeda and Yuji Matsumoto},
  booktitle={EMNLP},
  year={2020}
}
```

## Contact Info

Please submit a GitHub issue or send an e-mail to Ikuya Yamada
(`ikuya@ousia.jp`) for help or issues using LUKE.
