"""
A small spatio-temporal network, implemented from scratch in NumPy.

Why from scratch rather than a deep-learning framework: the network is tiny
(~10k parameters), inference must ship inside a standalone executable where a
framework would multiply the size twenty-fold, and every gradient here is
checked against finite differences in the test suite -- which is a stronger
correctness statement than "the framework is probably right".

Why this architecture: the input is a stack of K consecutive image patches
centred on one track. A single patch cannot distinguish the beacon from a star,
*by design* -- every point source in the simulator is rendered through the same
PSF precisely so that no single-frame cue exists. What separates them lives in
time: the beacon's pulsing and its motion against the star field. So the
network reads each frame with one shared spatial convolution (PSF shape), then
convolves along time (modulation and consistency), then classifies:

    input  (K, P, P)
      -> shared Conv2D 3x3, C channels, ReLU     spatial: is it PSF-shaped?
      -> per-frame global average pool -> (K, C)
      -> temporal Conv1D over K, width 3, ReLU   temporal: how does it change?
      -> global average pool -> (C2,)
      -> dense -> logit

Training is full-batch Adam on the binary cross-entropy; at this parameter
count that converges in seconds and removes every mini-batching knob.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np


def _he(rng, *shape):
    fan_in = int(np.prod(shape[1:])) if len(shape) > 1 else shape[0]
    return rng.normal(0.0, np.sqrt(2.0 / max(fan_in, 1)), shape)


class TemporalPatchNet:
    """Binary classifier over (K, P, P) patch stacks."""

    def __init__(self, frames: int = 8, patch: int = 11,
                 c_spatial: int = 8, c_temporal: int = 16, seed: int = 0):
        self.K, self.P = int(frames), int(patch)
        rng = np.random.default_rng(seed)
        self.params: Dict[str, np.ndarray] = {
            "Ws": _he(rng, c_spatial, 1, 3, 3),          # spatial conv
            "bs": np.zeros(c_spatial),
            "Wt": _he(rng, c_temporal, c_spatial, 3),    # temporal conv
            "bt": np.zeros(c_temporal),
            "Wd": _he(rng, 1, c_temporal),               # dense
            "bd": np.zeros(1),
        }
        self._adam_m = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._adam_v = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._adam_t = 0

    # ---- forward ---------------------------------------------------------
    @staticmethod
    def _conv2d(x, W, b):
        """x (N,K,P,P) -> (N,K,C,P-2,P-2). Small kernels: unrolled loop."""
        N, K, P, _ = x.shape
        C = W.shape[0]
        out = np.zeros((N, K, C, P - 2, P - 2))
        for i in range(3):
            for j in range(3):
                patch = x[:, :, i:i + P - 2, j:j + P - 2]
                out += patch[:, :, None] * W[None, None, :, 0, i, j, None, None]
        return out + b[None, None, :, None, None]

    @staticmethod
    def _conv1d(x, W, b):
        """x (N,K,C) -> (N,K-2,C2), kernel width 3 over the K axis."""
        N, K, C = x.shape
        C2 = W.shape[0]
        out = np.zeros((N, K - 2, C2))
        for i in range(3):
            out += np.einsum("nkc,dc->nkd", x[:, i:i + K - 2, :], W[:, :, i])
        return out + b[None, None, :]

    def forward(self, x: np.ndarray, keep: bool = False):
        """x: (N, K, P, P), already normalised. Returns logits (N,)."""
        z1 = self._conv2d(x, self.params["Ws"], self.params["bs"])
        a1 = np.maximum(z1, 0.0)
        p1 = a1.mean(axis=(3, 4))                                   # (N,K,C)
        z2 = self._conv1d(p1, self.params["Wt"], self.params["bt"])
        a2 = np.maximum(z2, 0.0)
        p2 = a2.mean(axis=1)                                        # (N,C2)
        logits = p2 @ self.params["Wd"].T + self.params["bd"]       # (N,1)
        if keep:
            self._cache = (x, z1, a1, p1, z2, a2, p2)
        return logits[:, 0]

    def predict(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.forward(x)))

    # ---- backward --------------------------------------------------------
    def _backward(self, dlogits: np.ndarray) -> Dict[str, np.ndarray]:
        x, z1, a1, p1, z2, a2, p2 = self._cache
        N, K, P, _ = x.shape
        g: Dict[str, np.ndarray] = {}
        dl = dlogits[:, None]                                       # (N,1)
        g["Wd"] = dl.T @ p2
        g["bd"] = dl.sum(axis=0)
        dp2 = dl @ self.params["Wd"]                                # (N,C2)
        da2 = np.repeat(dp2[:, None, :], a2.shape[1], axis=1) / a2.shape[1]
        dz2 = da2 * (z2 > 0)
        g["Wt"] = np.zeros_like(self.params["Wt"])
        for i in range(3):
            g["Wt"][:, :, i] = np.einsum("nkd,nkc->dc", dz2, p1[:, i:i + z2.shape[1], :])
        g["bt"] = dz2.sum(axis=(0, 1))
        dp1 = np.zeros_like(p1)
        for i in range(3):
            dp1[:, i:i + z2.shape[1], :] += np.einsum("nkd,dc->nkc", dz2,
                                                      self.params["Wt"][:, :, i])
        # undo the spatial mean pool
        Pm = a1.shape[3]
        da1 = dp1[:, :, :, None, None] * np.ones((1, 1, 1, Pm, Pm)) / (Pm * Pm)
        dz1 = da1 * (z1 > 0)
        g["Ws"] = np.zeros_like(self.params["Ws"])
        for i in range(3):
            for j in range(3):
                patch = x[:, :, i:i + Pm, j:j + Pm]
                g["Ws"][:, 0, i, j] = np.einsum("nkcpq,nkpq->c", dz1, patch)
        g["bs"] = dz1.sum(axis=(0, 1, 3, 4))
        return g

    # ---- training --------------------------------------------------------
    def train(self, x: np.ndarray, y: np.ndarray, epochs: int = 300,
              lr: float = 3e-3, weight_decay: float = 1e-4,
              verbose: bool = False) -> List[float]:
        """Full-batch Adam on binary cross-entropy. Returns the loss history."""
        history = []
        n = len(y)
        for epoch in range(epochs):
            logits = self.forward(x, keep=True)
            prob = 1.0 / (1.0 + np.exp(-logits))
            eps = 1e-9
            loss = float(-np.mean(y * np.log(prob + eps)
                                  + (1 - y) * np.log(1 - prob + eps)))
            history.append(loss)
            dlogits = (prob - y) / n
            grads = self._backward(dlogits)
            self._adam_t += 1
            for key, grad in grads.items():
                grad = grad + weight_decay * self.params[key]
                self._adam_m[key] = 0.9 * self._adam_m[key] + 0.1 * grad
                self._adam_v[key] = 0.999 * self._adam_v[key] + 0.001 * grad ** 2
                m_hat = self._adam_m[key] / (1 - 0.9 ** self._adam_t)
                v_hat = self._adam_v[key] / (1 - 0.999 ** self._adam_t)
                self.params[key] -= lr * m_hat / (np.sqrt(v_hat) + 1e-8)
            if verbose and epoch % 50 == 0:
                print(f"  epoch {epoch:4d}  loss {loss:.4f}")
        return history

    # ---- persistence -----------------------------------------------------
    def save(self, path: str) -> None:
        np.savez(path, K=self.K, P=self.P, **self.params)

    @classmethod
    def load(cls, path: str) -> "TemporalPatchNet":
        data = np.load(path)
        net = cls(frames=int(data["K"]), patch=int(data["P"]),
                  c_spatial=data["Ws"].shape[0], c_temporal=data["Wt"].shape[0])
        for key in net.params:
            net.params[key] = data[key]
        return net


def normalise_stack(stack: np.ndarray) -> np.ndarray:
    """
    Per-stack normalisation: zero median, unit robust scale.

    Per-stack rather than global, so the classifier sees shape and modulation
    rather than absolute brightness -- brightness is the one cue that must NOT
    be learned, because a decoy can be brighter than the beacon.
    """
    stack = stack.astype(np.float64)
    med = np.median(stack)
    scale = np.median(np.abs(stack - med)) * 1.4826 + 1e-6
    return (stack - med) / scale
