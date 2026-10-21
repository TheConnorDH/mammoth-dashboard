"""Season simulation for every team from power ratings + home ice (validated win/OT model; config/winprob_params.json).
Each simulated season draws every team's true strength once (from its rating and uncertainty), then plays
every remaining game: P(home win) = logistic(a + b*diff), P(overtime) = logistic(c + d*|diff|),
P(home win | OT) = logistic(e + f*diff); OT/shootout loser gets 1 point."""
import numpy as np


def _lg(x):
    return 1 / (1 + np.exp(-x))


def game_probs(diff, wp):
    a, b = wp["win"]; c, d = wp["ot"]; e, f = wp["otwin"]
    pwin = _lg(a + b * diff); pot = _lg(c + d * np.abs(diff)); potw = _lg(e + f * diff)
    p_reg_home = np.clip(pwin - pot * potw, 0, 1)
    return p_reg_home, pot, potw


def simulate(ratings, sds, points, remaining, wp, conf=None, div=None, sims=10000, seed=11):
    teams = sorted(ratings)
    ix = {t: i for i, t in enumerate(teams)}
    rng = np.random.default_rng(seed)
    true = np.array([ratings[t] for t in teams])[None, :] + rng.normal(size=(sims, len(teams))) * np.array([sds[t] for t in teams])[None, :]
    pts = np.tile(np.array([points.get(t, 0) for t in teams], float), (sims, 1))
    for g in remaining:
        h, a = g[0], g[1]; shift = g[2] if len(g) > 2 else 0.0     # shift: rest (back-to-back) edge, in rating-difference units
        if h not in ix or a not in ix:
            continue
        i, j = ix[h], ix[a]
        diff = true[:, i] - true[:, j] + shift
        preg, pot, potw = game_probs(diff, wp)
        u = rng.random(sims); v = rng.random(sims)
        reg_home = u < preg
        ot = (u >= preg) & (u < preg + pot)
        ot_home = ot & (v < potw)
        reg_away = ~reg_home & ~ot
        pts[:, i] += 2 * reg_home + 2 * ot_home + 1 * (ot & ~ot_home)
        pts[:, j] += 2 * reg_away + 2 * (ot & ~ot_home) + 1 * ot_home
    out = {t: {"mean": float(pts[:, ix[t]].mean()), "lo95": float(np.percentile(pts[:, ix[t]], 2.5)), "hi95": float(np.percentile(pts[:, ix[t]], 97.5)),
               "lo50": float(np.percentile(pts[:, ix[t]], 25)), "hi50": float(np.percentile(pts[:, ix[t]], 75)),
               "lo80": float(np.percentile(pts[:, ix[t]], 10)), "hi80": float(np.percentile(pts[:, ix[t]], 90))} for t in teams}
    if conf and div:
        tie = rng.random(pts.shape) * 0.01
        score = pts + tie
        made = np.zeros_like(pts, bool); divwin = np.zeros_like(pts, bool); cut = {}
        for cf in set(conf.values()):
            members = [t for t in teams if conf.get(t) == cf]
            divs = sorted({div[t] for t in members})
            top3 = np.zeros_like(pts, bool)
            for dv in divs:
                dm = [ix[t] for t in members if div[t] == dv]
                order = np.argsort(-score[:, dm], axis=1)
                for k in range(min(3, len(dm))):
                    top3[np.arange(sims), np.array(dm)[order[:, k]]] = True
                divwin[np.arange(sims), np.array(dm)[order[:, 0]]] = True
            cm = np.array([ix[t] for t in members])
            rest = np.where(top3[:, cm], -1e9, score[:, cm])
            order = np.argsort(-rest, axis=1)
            wc = np.zeros_like(pts, bool)
            for k in range(2):
                wc[np.arange(sims), cm[order[:, k]]] = True
            made |= top3 | wc
            # this season's playoff line in the conference: points of the last team in (per simulated season)
            last_in = np.where(made[:, cm], pts[:, cm], np.inf).min(axis=1)
            cut[cf] = {"median": float(np.median(last_in)), "mean": float(last_in.mean()),
                       "lo80": float(np.percentile(last_in, 10)), "hi80": float(np.percentile(last_in, 90))}
        for t in teams:
            out[t]["playoff"] = float(made[:, ix[t]].mean()); out[t]["division"] = float(divwin[:, ix[t]].mean())
        out["_cut"] = cut
        out["_hist"] = {t: np.bincount(pts[:, ix[t]].astype(int), minlength=200)[:200].tolist() for t in teams}
    return out
