"""
Choose the two score cutoffs that best reproduce the FINAL ratings a lab has already given
"""

from dataclasses import dataclass

import numpy as np

# Linear weights: good against bad is twice as far apart as either against other
_W = np.abs(np.subtract.outer(np.arange(3), np.arange(3))) / 2


@dataclass(frozen=True)
class Calibration:
    cut_bad: float
    cut_other: float
    kappa: float
    accuracy: float
    loo_kappa: float
    loo_accuracy: float


def candidate_cutoffs(scores):
    """(cutoffs, gap widths): the middle of each gap between scores, and half a point past either end."""
    s = np.unique(scores)
    edges = np.concatenate([s[:1] - 1, s, s[-1:] + 1])
    return (edges[:-1] + edges[1:]) / 2, np.diff(edges)


def predict(scores, veto, cut_bad, cut_other):
    """FINAL codes for arrays of cutoff pairs: rows follow the pairs, columns the runs."""
    cut_bad, cut_other = np.atleast_1d(cut_bad)[:, None], np.atleast_1d(cut_other)[:, None]
    p = np.where(scores[None] >= cut_bad, 2, np.where(scores[None] >= cut_other, 1, 0))
    return np.where(veto[None], 2, p)


def kappa_accuracy(y, P):
    """Linearly weighted kappa and accuracy of each row of predictions P against the ratings y."""
    cells = y[None] * 3 + P
    O = np.stack([(cells == j).sum(axis=1) for j in range(9)], axis=1).reshape(-1, 3, 3).astype(float)
    n = O.sum(axis=(1, 2))
    E = O.sum(axis=2)[:, :, None] * O.sum(axis=1)[:, None, :] / n[:, None, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        kappa = 1 - (_W * O).sum(axis=(1, 2)) / (_W * E).sum(axis=(1, 2))
    return kappa, np.trace(O, axis1=1, axis2=2) / n


def choose(y, scores, veto, current):
    """The pair with the highest kappa, then accuracy; among equals, the one nearest the cutoffs in use."""
    c, width = candidate_cutoffs(scores)
    jb, jo = np.meshgrid(np.arange(len(c)), np.arange(len(c)), indexing="ij")
    keep = jo <= jb
    jb, jo = jb[keep], jo[keep]
    # Both cutoffs in one gap leave no run in the other band; they are then written a quarter gap apart
    kappa, accuracy = kappa_accuracy(y, predict(scores, veto, c[jb], c[jo]))
    same = jb == jo
    bad = np.where(same, c[jb] + width[jb] / 4, c[jb])
    other = np.where(same, c[jo] - width[jo] / 4, c[jo])
    kappa = np.nan_to_num(kappa, nan=-np.inf)
    distance = np.abs(bad - current[0]) + np.abs(other - current[1])
    best = np.lexsort((bad, distance, -accuracy, -kappa))[0]
    return bad[best], other[best], kappa[best], accuracy[best]


def calibrate(y, scores, veto, groups, current):
    """Cutoffs from all rated runs, and the agreement when each group's cutoffs come from the other groups."""
    y, scores, veto, groups = map(np.asarray, (y, scores, veto, groups))
    cut_bad, cut_other, kappa, accuracy = choose(y, scores, veto, current)
    held_out = np.empty(len(y), int)
    for g in np.unique(groups):
        test = groups == g
        b, o, _, _ = choose(y[~test], scores[~test], veto[~test], current)
        held_out[test] = predict(scores[test], veto[test], b, o)[0]
    loo_kappa, loo_accuracy = kappa_accuracy(y, held_out[None])
    return Calibration(_tidy(cut_bad), _tidy(cut_other), float(kappa), float(accuracy),
                       float(loo_kappa[0]), float(loo_accuracy[0]))


def _tidy(value):
    """A cutoff as written to the config: 10 rather than 10.0, and no float noise."""
    value = round(float(value), 6)
    return int(value) if value.is_integer() else value
