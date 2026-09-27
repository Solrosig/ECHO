"""Data access for the figure scripts. Reads the tables in the repository's `research/` folder
(in the evidence bundle they sit in `04 Data - acoustic` and `05 Data - listener and
instruments` beside `03 Figures`). Nothing is computed here beyond one join."""
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
D04 = ROOT / "research"   # bundle: 04 Data - acoustic
D05 = ROOT / "research"   # bundle: 05 Data - listener and instruments

NAME = {"chatterbox": "Chatterbox", "cosyvoice2": "CosyVoice 2", "espeak": "eSpeak NG",
        "kokoro": "Kokoro", "parlertts": "Parler-TTS", "pyttsx3": "Platform wrapper",
        "sapi5xml": "Platform engine", "styletts2": "StyleTTS 2", "zipvoice": "ZipVoice"}
TGT = {"happy": "Happy", "upset": "Upset", "sad": "Sad", "calm": "Calm"}


def contrasts():
    """288 paired contrasts: one row per participant, configuration and emotion target."""
    return pd.read_csv(D05 / "contrasts.csv")


def confusion():
    """Requested against rated quadrant, row percentages."""
    return pd.read_csv(D05 / "confusion_preset.csv", index_col=0)


def deltas():
    """Acoustic deltas, preset minus matched neutral, per configuration and emotion target."""
    return pd.read_csv(D04 / "acoustics_v2_deltas.csv")


def bridge():
    """Acoustic separation per configuration joined to the listener and UTMOS scorecard."""
    a = pd.read_csv(D04 / "acoustic_separation_by_engine.csv")
    s = pd.read_csv(D05 / "scorecard_frozen45.csv")
    b = a.merge(s[["engine", "auto_utmos", "lis_preset_naturalness", "lis_imp_arousal",
                   "lis_imp_valence", "lis_improvement"]], on="engine")
    b["label"] = b.engine.map(NAME)
    return b


def spearman(x, y):
    """Spearman rank correlation with the two-sided t-approximation p-value, as in SciPy."""
    try:
        from scipy import stats
        r, p = stats.spearmanr(x, y)
        return float(r), float(p)
    except ImportError:
        pass
    import math
    import numpy as np
    rx = pd.Series(x).rank().to_numpy(); ry = pd.Series(y).rank().to_numpy()
    r = float(np.corrcoef(rx, ry)[0, 1]); n = len(rx)
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return r, _t_sf_two_sided(t, n - 2)


def _betacf(a, b, x, itmax=200, eps=3e-14):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300); h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300); c = 1 + aa / (c if abs(c) > 1e-300 else 1e-300); h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300); c = 1 + aa / (c if abs(c) > 1e-300 else 1e-300)
        de = d * c; h *= de
        if abs(de - 1) < eps:
            break
    return h


def _betainc(a, b, x):
    import math
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def _t_sf_two_sided(t, df):
    x = df / (df + t * t)
    return _betainc(df / 2, 0.5, x)
