# -*- coding: utf-8 -*-
"""
Preprocessors.
"""
import itertools
import re

import MeCab
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.externals import joblib
from keras.utils.np_utils import to_categorical
from keras.preprocessing.sequence import pad_sequences

UNK = '<UNK>'
PAD = '<PAD>'
# t = MeCab.Tagger('-Owakati')
# t = MeCab.Tagger('-Owakati -d /usr/local/lib/mecab/dic/mecab-ipadic-neologd')
t = MeCab.Tagger('-d /usr/local/lib/mecab/dic/mecab-ipadic-neologd')


def tokenize(text):
    words, poses = [], []
    chunks = t.parse(text.rstrip()).splitlines()[:-1]  # Skip EOS
    for chunk in chunks:
        if chunk == '':
            continue
        chunk_splitted = chunk.split('\t')
        surface = chunk_splitted[0]
        feature = chunk_splitted[1]
        feature = feature.split(',')
        pos = '-'.join(feature[:3])

        words.append(surface)
        poses.append(pos)

    return words, poses


def normalize_number(text):
    return re.sub(r'[0-9０１２３４５６７８９]', r'0', text)


def is_hiragana(ch):
    return 0x3040 <= ord(ch) <= 0x309F


def is_katakana(ch):
    return 0x30A0 <= ord(ch) <= 0x30FF


def get_character_type(ch):
    if ch.isspace():
        return 1
    elif ch.isdigit():
        return 2
    elif ch.islower():
        return 3
    elif ch.isupper():
        return 4
    elif is_hiragana(ch):
        return 5
    elif is_katakana(ch):
        return 6
    else:
        return 7


class StaticPreprocessor(BaseEstimator, TransformerMixin):

    def __init__(self, lowercase=True, num_norm=True, vocab_init=None):
        self._lowercase = lowercase
        self._num_norm = num_norm
        self._vocab_init = vocab_init or {}
        self.word_dic = {PAD: 0, UNK: 1}
        self.char_dic = {PAD: 0, UNK: 1}
        self.pos_dic = {PAD: 0, UNK: 1}
        self.label_dic = {PAD: 0}
        self.bies_dic = {'B': 1, 'I': 2, 'E': 3, 'S': 4}
        self.char_type_dic = {PAD: 0}

    def fit(self, X, y=None):
        for doc in X:
            text = ''.join(doc)
            if self._lowercase:
                text = text.lower()
            if self._num_norm:
                text = normalize_number(text)
            words, poses = tokenize(text)
            for w in words:
                if w in self.word_dic:
                    continue
                self.word_dic[w] = len(self.word_dic)
                for c in w:
                    if c in self.char_dic:
                        continue
                    self.char_dic[c] = len(self.char_dic)

            for pos in poses:
                if pos in self.pos_dic:
                    continue
                self.pos_dic[pos] = len(self.pos_dic)

        # create label dictionary
        for t in set(itertools.chain(*y)):
            self.label_dic[t] = len(self.label_dic)

        return self

    def transform(self, X, y=None):
        x_words = []
        x_chars = []
        x_bies = []
        x_poses = []
        x_types = []
        for doc in X:
            text = ''.join(doc)
            if self._lowercase:
                text = text.lower()
            if self._num_norm:
                text = normalize_number(text)
            words, poses = tokenize(text)
            word_ids = [[self.word_dic.get(w, self.word_dic[UNK]) for _ in range(len(w))]
                        for w in words]
            char_ids = [self._get_char_ids(w) for w in words]
            bies_ids = [self.get_bies(w) for w in words]
            pos_ids = [[self.pos_dic.get(p, self.pos_dic[UNK]) for _ in range(len(w))]
                       for w, p in zip(words, poses)]
            char_types = [self.get_char_types(w) for w in words]
            word_ids = list(itertools.chain(*word_ids))
            char_ids = list(itertools.chain(*char_ids))
            bies_ids = list(itertools.chain(*bies_ids))
            pos_ids = list(itertools.chain(*pos_ids))
            char_types = list(itertools.chain(*char_types))
            x_words.append(np.array(word_ids, dtype=np.int32))
            x_chars.append(np.array(char_ids, dtype=np.int32))
            x_bies.append(np.array(bies_ids, dtype=np.int32))
            x_poses.append(np.array(pos_ids, dtype=np.int32))
            x_types.append(np.array(char_types, dtype=np.int32))

            assert len(char_ids) == len(word_ids)
            assert len(bies_ids) == len(word_ids)
            assert len(pos_ids) == len(word_ids)

        if y is not None:
            y = np.array([[self.label_dic[t] for t in sent] for sent in y])

        inputs = [np.array(x_words), np.array(x_chars), np.array(x_bies), np.array(x_poses), np.array(x_types)]

        return (inputs, y) if y is not None else inputs

    def fit_transform(self, X, y=None, **fit_params):
        return self.fit(X, y).transform(X, y)

    def inverse_transform(self, X=None, docs=None):
        if X is not None:
            id2char = {i: c for c, i in self.char_dic.items()}
            return [[id2char[c] for c in sent] for sent in X]
        id2label = {i: t for t, i in self.label_dic.items()}

        return [[id2label[t] for t in doc] for doc in docs]

    def _get_char_ids(self, word):
        return [self.char_dic.get(c, self.char_dic[UNK]) for c in word]

    def get_char_types(self, word):
        return [get_character_type(c) for c in word]

    def get_bies(self, word):
        if len(word) == 1:
            return [self.bies_dic['S']]
        res = [self.bies_dic['I']] * len(word)
        res[0] = self.bies_dic['B']
        res[-1] = self.bies_dic['E']
        return res

    def save(self, file_path):
        joblib.dump(self, file_path)

    @classmethod
    def load(cls, file_path):
        p = joblib.load(file_path)

        return p


class DynamicPreprocessor(BaseEstimator, TransformerMixin):

    def __init__(self, n_labels):
        self.n_labels = n_labels

    def transform(self, X, y=None):
        words, chars, bies, poses, types = X
        words = pad_sequences(words, padding='post')
        chars = pad_sequences(chars, padding='post')
        bies = pad_sequences(bies, padding='post')
        poses = pad_sequences(poses, padding='post')
        types = pad_sequences(types, padding='post')

        if y is not None:
            y = pad_sequences(y, padding='post')
            y = np.array([to_categorical(y_, self.n_labels) for y_ in y])
        sents = [words, chars, bies, poses, types]

        return (sents, y) if y is not None else sents

    def save(self, file_path):
        joblib.dump(self, file_path)

    @classmethod
    def load(cls, file_path):
        p = joblib.load(file_path)

        return p