from config import Config as conf
from tqdm import tqdm
import tensorflow as tf
import numpy as np
import os
import sys
from gensim import models
if sys.version.split()[0].startswith("2"): #Python2
    import cPickle as pkl
else:
    import pickle as pkl

class preprocessor:
    tokens = {}
    top_20k = []
    word2idx = {}
    idx2word = {}
    lines = []
    preprocessed_data = []
    loaded = False

    def __init__(self, dir_name = None):
        if dir_name == None:
            self.tokens = {}
            self.top_20k = []
            self.word2idx = {}
            self.idx2word = {}
            self.lines = []
            self.preprocessed_data = []
            self.loaded = False
        else:
            self.tokens = {}
            self.top_20k =  pkl.load(open(dir_name+"/top_20k.pkl"))
            self.word2idx = pkl.load(open(dir_name+"/word2idx.pkl"))
            self.idx2word = pkl.load(open(dir_name+"/idx2word.pkl"))
            self.lines =    pkl.load(open(dir_name+"/lines.pkl"))
            self.preprocessed_data = lines
            self.loaded = True

    def preprocess(self, filename):
        if not self.loaded:
            print("Reading file")
            self.extract_tokens(filename)
            print("Extracting top 20k words")
            self.get_top20k()
            del self.tokens
            print("Creating word to ID mapping")
            self.create_mapping()
            print("Dumping the pkl files")
            if not os.path.exists(conf.pkl_dir):
                os.makedirs(conf.pkl_dir)
            print("Dumping top_20k")
            pkl.dump(self.top_20k, open(conf.pkl_dir + "/top_20k.pkl", "wb"))
            print("Dumping word2idx")
            pkl.dump(self.word2idx, open(conf.pkl_dir + "/word2idx.pkl", "wb"))
            print("Dumping idx2word")
            pkl.dump(self.idx2word, open(conf.pkl_dir + "/idx2word.pkl", "wb"))
            # print "Dumping lines"
            # pkl.dump(self.lines, open("lines.pkl", "w"))
        else:
            print("All loaded, nothing to do!")

    def extract_tokens(self, filename):
        self.tokens = {}
        self.lines = []
        total_lines = 0
        overflow_lines = 0
        with open(filename) as f:
            for line in tqdm(f, total = 2000000):
                total_lines+=1
                words = line.strip().split(" ")
                if len(words) > 28:
                    overflow_lines+=1
                    continue
                else:
                    self.lines.append(words)
                    for word in words:
                        if word in self.tokens:
                            self.tokens[word] += 1
                        else:
                            self.tokens[word] = 1
            assert len(self.lines) + overflow_lines == total_lines
            print("total lines: {}".format(total_lines))
            print("overflow lines ( > 28 words): {}".format(overflow_lines))

    def get_top20k(self):
        top_words = sorted(self.tokens, key = self.tokens.get, reverse = True)[:conf.top_words]
        top_words.extend(["<bos>", "<eos>", "<pad>", "<unk>"])
        assert len(top_words) == 20000
        self.top_20k = top_words

    def create_mapping(self):
        for idx, word in enumerate(self.top_20k):
            self.word2idx[word] = idx
            self.idx2word[idx] = word

    def lines2idx(self):
        for i in tqdm(xrange(len(self.lines))):
            line = self.lines[i]
            if len(line) < 28:
                line = line + ["<pad>"]*(28 - len(line))
            line = ["<bos>"] + line + ["<eos>"]
            assert len(line) == 30
            line = [[self.word2idx.get(word, self.word2idx["<unk>"])] for word in line]
            self.lines[i] = line
        self.preprocessed_data = self.lines

    def get_batch(self, filename = None):
        if filename == None:
            lines = self.lines
            np.random.shuffle(lines)
        else:
            lines = []
            with open(filename) as f:
                for line in f:
                    lines.append(line.strip().split(" "))
            # We miss a few lines in the end because len(lines) % 64 != 0, 
            # so just add stuff to the back, and throw away the last results before reporting
            num_lines = len(lines)
            lines.extend(lines[:conf.batch_size - (num_lines % conf.batch_size)])
            assert len(lines) % conf.batch_size == 0
        for i in range(0, 64 * (len(lines) // 64), conf.batch_size):
            new_batch = []
            batch = lines[i: i+64]
            for line in batch:
                if len(line) > 28:
                    continue
                line = ["<bos>"] + line + ["<eos>"]
                if len(line) < 30:
                    line = line + ["<pad>"]*(30 - len(line))
                assert len(line) == 30
                line = [[self.word2idx.get(word, self.word2idx["<unk>"])] for word in line]
                new_batch.append(line)
            batch = new_batch
            batch = np.asarray(batch)
            if batch.shape != (64, 30, 1):
                print(batch.shape)
            assert batch.shape == (64, 30, 1)
            yield batch[:, :-1,:], batch[:, 1:, :]


    def load_embedding(self, session, emb, dim_embedding = conf.embed_size,
        path = conf.word2vec_path):
        vocab = self.word2idx
        print("Loading external embeddings from {}".format(path))
        model = models.KeyedVectors.load_word2vec_format(path, binary=False)
        external_embedding = np.zeros(shape=(conf.vocab_size, dim_embedding))
        matches = 0
        for tok, idx in tqdm(vocab.items()):
            if tok in model.vocab:
                external_embedding[idx] = model[tok]
                matches += 1
            else:
                print("{} not in embedding file" .format(tok))
                external_embedding[idx] = np.random.uniform(low=-0.25, high=0.25, size=dim_embedding)

        print("{} words out of {} could be loaded".format(matches, conf.vocab_size))

        pretrained_embeddings = tf.placeholder(tf.float32, [None, None])
        assign_op = emb.assign(pretrained_embeddings)
        session.run(assign_op, {pretrained_embeddings: external_embedding})
