"""Small L2 logistic regression in numpy: transparent, every weight printable."""
import json, numpy as np
from .features import FEATURES

class RiskModel:
    def __init__(self, l2=1.0, features=None): self.l2, self.features = l2, list(features or FEATURES)
    def fit(self, X, y, iters=3000, lr=0.1):
        X = X[self.features].values.astype(float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        w, b, n = np.zeros(Z.shape[1]), np.log(y.mean() / (1 - y.mean())), len(y)
        for _ in range(iters):
            p = 1 / (1 + np.exp(-(Z @ w + b)))
            w -= lr * (Z.T @ (p - y) / n + self.l2 * w / n)
            b -= lr * (p - y).mean()
        self.w, self.b = w, b
        return self
    def predict(self, X):
        Z = (X[self.features].values.astype(float) - self.mu) / self.sd
        return 1 / (1 + np.exp(-(Z @ self.w + self.b)))
    def contributions(self, xrow):
        z = (np.array([xrow[f] for f in self.features], float) - self.mu) / self.sd
        return dict(zip(self.features, z * self.w))
    def weights(self): return {f: round(float(w), 3) for f, w in zip(self.features, self.w)}
    def save(self, path):
        json.dump({"mu": self.mu.tolist(), "sd": self.sd.tolist(), "w": self.w.tolist(), "b": self.b, "features": self.features}, open(path, "w"), indent=1)
    @classmethod
    def load(cls, path):
        d = json.load(open(path)); m = cls(features=d["features"])
        m.mu, m.sd, m.w, m.b = np.array(d["mu"]), np.array(d["sd"]), np.array(d["w"]), d["b"]
        return m

def auc(y, p):
    y, p = np.asarray(y), np.asarray(p)
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    pos = y == 1
    return (r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
