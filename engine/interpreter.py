# encoding: utf-8
"""
@author:  liaoxingyu
@contact: sherlockliao01@gmail.com
"""

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
from fastai.basic_data import *
from fastai.layers import *
from fastai.vision import *


class ReidInterpretation():
    "Interpretation methods for reid models."
    def __init__(self, learn, test_labels, num_q):
        self.learn,self.test_labels,self.num_q = learn,test_labels,num_q
        self.test_dl = learn.data.test_dl
        self.get_distmat()

    def get_distmat(self):
        pids = []
        camids = []
        for p,c in self.test_labels:
            pids.append(p)
            camids.append(c)
        self.q_pids = np.asarray(pids[:self.num_q])
        self.g_pids = np.asarray(pids[self.num_q:])
        self.q_camids = np.asarray(camids[:self.num_q])
        self.g_camids = np.asarray(camids[self.num_q:])

        feats, _ = self.learn.get_preds(DatasetType.Test, activ=Lambda(lambda x:x))
        feats = F.normalize(feats)
        qf = feats[:self.num_q]
        gf = feats[self.num_q:]
        m, n = qf.shape[0], gf.shape[0]

        # Cosine distance
        distmat = torch.mm(qf, gf.t())
        self.distmat = to_np(distmat)
        self.indices = np.argsort(-self.distmat, axis=1)
        self.matches = (self.g_pids[self.indices] == self.q_pids[:, np.newaxis]).astype(np.int32)

    def get_matched_result(self, q_index):
        q_pid = self.q_pids[q_index]
        q_camid = self.q_camids[q_index]

        order = self.indices[q_index]
        remove = (self.g_pids[order] == q_pid) & (self.g_camids[order] == q_camid)
        keep = np.invert(remove)
        cmc = self.matches[q_index][keep]
        sort_idx = order[keep]
        return cmc, sort_idx
        
    def plot_rank_result(self, q_idx, top=5, title="Rank result"):
        cmc, sort_idx = self.get_matched_result(q_idx)

        fig,axes = plt.subplots(1, top+1, figsize=(15, 5))
        fig.suptitle('query  similarity/true(false)')
        query_im,cl=self.test_dl.dataset[q_idx]
        query_im.show(ax=axes.flat[0], title='query')
        for i in range(top):
            g_idx = self.num_q + sort_idx[i] 
            im,cl = self.test_dl.dataset[g_idx]
            if cmc[i] == 1:
                label='true'
                axes.flat[i+1].add_patch(plt.Rectangle(xy=(0, 0), width=im.size[1]-1, height=im.size[0]-1, 
                                         edgecolor=(1, 0, 0), fill=False, linewidth=5))
            else:
                label='false'
                axes.flat[i+1].add_patch(plt.Rectangle(xy=(0, 0), width=im.size[1]-1, height=im.size[0]-1, 
                                         edgecolor=(0, 0, 1), fill=False, linewidth=5))
            im.show(ax=axes.flat[i+1], title=f'{self.distmat[q_idx, sort_idx[i]]:.3f} / {label}')
        return fig

    def get_top_error(self):
        # Iteration over query ids and store query gallery similarity
        similarity_score = namedtuple('similarityScore', 'query gallery sim cmc')
        storeCorrect = []
        storeWrong = []
        for q_index in range(self.num_q):
            cmc, sort_idx = self.get_matched_result(q_index)
            single_item = similarity_score(query=q_index, gallery=[self.num_q + sort_idx[i] for i in range(5)], 
                                           sim=[self.distmat[q_index, sort_idx[i]] for i in range(5)],
                                           cmc=cmc[:5])
            if cmc[0] == 1:
                storeCorrect.append(single_item)
            else:
                storeWrong.append(single_item)
        storeCorrect.sort(key=lambda x: x.sim[0])
        storeWrong.sort(key=lambda x: x.sim[0], reverse=True)

        self.storeCorrect = storeCorrect
        self.storeWrong = storeWrong

    def plot_top_error(self, topK=5, positive=True):
        if not hasattr(self, 'storeCorrect'):
            self.get_top_error()

        if positive:
            img_list = self.storeCorrect
        else:
            img_list = self.storeWrong
        # Rank top error results, which means negative sample with largest similarity
        # and positive sample with smallest similarity
        fig,axes = plt.subplots(topK, 6, figsize=(15, 4*topK))
        fig.suptitle('query similarity/true(false)')
        for i in range(topK):
            q_idx,g_idxs,sim,cmc = img_list[i]
            query_im,cl = self.test_dl.dataset[q_idx]
            query_im.show(ax=axes[i, 0], title='query')
            for j,g_idx in enumerate(g_idxs):
                im,cl = self.test_dl.dataset[g_idx]
                if cmc[j] == 1:
                    label='true'
                    axes[i,j+1].add_patch(plt.Rectangle(xy=(0, 0), width=im.size[1]-1, height=im.size[0]-1, 
                                          edgecolor=(1, 0, 0), fill=False, linewidth=5))
                else:
                    label='false'
                    axes[i, j+1].add_patch(plt.Rectangle(xy=(0, 0), width=im.size[1]-1, height=im.size[0]-1, 
                                           edgecolor=(0, 0, 1), fill=False, linewidth=5))
                im.show(ax=axes[i,j+1], title=f'{sim[j]:.3f} / {label}')
            
        return fig

    def plot_positve_negative_dist(self):
        pos_sim, neg_sim = [], []
        for i, q in enumerate(self.q_pids):
            cmc, sort_idx = self.get_matched_result(i)  # remove same id in same camera
            for j in range(len(cmc)):
                if cmc[j] == 1:
                    pos_sim.append(self.distmat[i,sort_idx[j]])
                else:
                    neg_sim.append(self.distmat[i,sort_idx[j]])
        fig = plt.figure(figsize=(10,5))
        plt.hist(pos_sim, bins=80, alpha=0.7, density=True, color='red', label='positive')
        plt.hist(neg_sim, bins=80, alpha=0.5, density=True, color='blue', label='negative')
        plt.xticks(np.arange(-0.3, 0.8, 0.1))
        plt.title('posivie and negative pair distribution')
        return pos_sim, neg_sim

    def plot_same_cam_diff_cam_dist(self):
        same_cam, diff_cam = [], []
        for i, q in enumerate(self.q_pids):
            q_camid = self.q_camids[i]

            order = self.indices[i]
            same = (self.g_pids[order] == q) & (self.g_camids[order] == q_camid)
            diff = (self.g_pids[order] == q) & (self.g_camids[order] != q_camid)
            sameCam_idx = order[same]
            diffCam_idx = order[diff]

            same_cam.extend(self.distmat[i, sameCam_idx])
            diff_cam.extend(self.distmat[i, diffCam_idx])

        fig = plt.figure(figsize=(10,5))
        plt.hist(same_cam, bins=80, alpha=0.7, density=True, color='red', label='same camera')
        plt.hist(diff_cam, bins=80, alpha=0.5, density=True, color='blue', label='diff camera')
        plt.xticks(np.arange(0.1, 1.0, 0.1))
        plt.title('posivie and negative pair distribution')
        return fig