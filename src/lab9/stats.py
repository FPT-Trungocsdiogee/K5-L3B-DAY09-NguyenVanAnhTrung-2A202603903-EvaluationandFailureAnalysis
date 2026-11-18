"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from math import comb
POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: {len(human)} human vs {len(judge)} judge labels")
    out = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h_pos = str(h).strip().upper() == POS
        j_pos = str(j).strip().upper() == POS
        if j_pos:
            out["tp" if h_pos else "fp"] += 1
        else:
            out["fn" if h_pos else "tn"] += 1
    return out


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    # TODO M2: precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when the denominator is 0
    conf_matrix = confusion(human, judge)
    tp = conf_matrix["tp"]
    tn = conf_matrix["tn"]
    fp = conf_matrix["fp"]
    fn = conf_matrix["fn"]
    if((tp + fp) == 0):
        precision = 0
    else:
        precision = tp / (tp + fp)
    if((tp + fn) == 0):
        recall = 0
    else:
        recall = tp / (tp + fn)
    return (precision, recall)
        #raise NotImplementedError


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    # TODO M2
    conf_matrix = confusion(human, judge)
    tp = conf_matrix["tp"]
    tn = conf_matrix["tn"]
    fp = conf_matrix["fp"]
    fn = conf_matrix["fn"]
    tu_so = 2 * ((tp * tn) - (fp * fn))
    mau_so = (tp + fp) * (fp +tn) + (tp + fn) * (fn + tn)
    if mau_so == 0:
        # mau_so == 0 <=> p_e == 1: human and judge both gave one constant label (or no rows at all)
        raise ValueError(
            f"Cohen's kappa is undefined (p_e == 1): human and judge use a single constant label "
            f"over {tp + fp + fn + tn} item(s) (tp={tp}, fp={fp}, fn={fn}, tn={tn}); "
            "a constant judge has no signal and fails calibration"
        )
    kappa = tu_so / mau_so
    return kappa 
    #raise NotImplementedError


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    # TODO M2: (p_obs + spec - 1) / (sens + spec - 1)
    tu_so = observed_rate + specificity - 1
    mau_so = sensitivity + specificity - 1
    if mau_so <= 0:
        # Youden's J = sens + spec - 1 <= 0: the judge is no better than a coin flip (or inverted)
        raise ValueError(
            f"Rogan-Gladen correction is undefined: sensitivity + specificity - 1 = {mau_so:.4f} <= 0 "
            f"(sensitivity={sensitivity}, specificity={specificity}); "
            "the judge is no better than chance and cannot correct the observed rate"
        )
    return min(1.0, max(0.0, tu_so / mau_so))
    # raise NotImplementedError


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"paired bootstrap needs the same items: {x.shape} vs {y.shape}")
    if x.size == 0:
        raise ValueError("paired bootstrap needs at least one item")
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)    # zero variance: scipy would return a degenerate/NaN interval

    def mean_diff(xs, ys, axis=-1):
        return np.mean(xs, axis=axis) - np.mean(ys, axis=axis)

    res = bootstrap((x, y), mean_diff, paired=True, vectorized=True, n_resamples=n_resamples,
                    confidence_level=confidence, method="percentile",
                    rng=np.random.default_rng(rng))
    lo, hi = res.confidence_interval
    return (float(mean_diff(x, y)), float(lo), float(hi))


def _check_k_args(n: int, c: int, k: int) -> None:
    """Valid only for 1 <= k <= n and 0 <= c <= n (c passing trials out of n)."""
    if n < 1 or k < 1 or k > n or c < 0 or c > n:
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n}, c={c}, k={k}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_k_args(n, c, k)
    return 1 - (comb(n-c, k)/comb(n, k))


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    # TODO M6
    _check_k_args(n, c, k)
    return comb(c, k)/comb(n, k)
