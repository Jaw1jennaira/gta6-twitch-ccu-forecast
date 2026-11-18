# Strategy

## The problem

Forecast Twitch concurrent viewers in the "Grand Theft Auto VI" category
for each hour 2..24 of release day (19 Nov 2026 UTC), as five quantiles
(5%, 25%, 50%, 75%, 95%), given only what is known at the end of hour 1.
Scored by mean pinball loss on the log scale. The forecast must beat both
house entries (the persistence baseline and the house AI-model forecast)
on the final day to take a prize.

## What the data says

Each case ships the full hourly Twitch curves of 42 past big launches
(SullyGnome hourly category averages, 14 days before to 3 days after each
release). Working in log space with the log-ratio curve
`L_h = ln(viewers_h / viewers_1)`:

1. **Release days have a shared diurnal shape.** Hour 1 (00:00-01:00 UTC)
   already has real viewership for rolling-midnight launches (New Zealand,
   Australia, Asia and Europe have unlocked; the UK unlocks at 00:00 UTC).
   Viewership dips in hours 3-11 (night in Europe, US not yet unlocked),
   then rises as the US comes online and Europe hits prime time, peaking
   around hours 18-22, then easing off.
2. **The shape depends on hour 1's size — strongly.** The correlation
   between `ln(hour-1)` and `L_h` reaches about -0.89 by hour 20. The
   biggest launches (ELDEN RING 875k, Cyberpunk 2077 852k in hour 1) stay
   almost flat all day (peak / hour-1 of 1.00-1.26); small hour-1 launches
   grow 2-3.5x by evening. A launch whose first hour already captured the
   global audience has nowhere left to grow.
3. **A linear fit extrapolates badly at GTA VI scale.** Fitting `L_h` on
   `ln(hour-1)` over all launches and extrapolating to a 1-2M hour 1
   predicts an evening collapse to ~0.2x hour 1 — an artefact of the
   simultaneous-global launches (tiny hour 1, huge growth) pulling the
   slope. The relationship saturates; the model must respect that.

## The model (`main.py`, standard library only, deterministic)

Two estimators of each hour's log-ratio quantiles, blended 50/50 in log
space, with the spread around the median widened 1.1x:

- **A. Kernel-weighted quantiles.** Per hour, the empirical quantiles of
  `L_h` across past launches, weighted by a Gaussian kernel on the distance
  between `ln(hour-1)` of the past launch and of this case (bandwidth 1.0
  log units). The forecast is anchored on launches of a similar size, so
  it saturates naturally instead of extrapolating. Launches flagged
  early-access-contaminated or weak in the case data count half.
- **B. Rolling-launch regression.** OLS of `L_h` on `ln(hour-1)` fitted
  only on rolling launches (peak / hour-1 <= 6 — midnight-local rolling
  unlocks, like GTA VI's), with quantiles from the empirical quantiles of
  its residuals.

If either component lacks enough launches it falls back to the other; if
both fail, the forecast is the house baseline's persistence shape. The
hour-1 print anchors the level; the model never uses the minute history,
top streams, or category tables, because those signals cannot be validated
against the hourly practice data.

## Validation

Practice answers were recovered from SullyGnome's public "Average
viewers" series for the four practice launches and verified to match each
case's hour-1 print exactly. The scorer is the rules' pinball loss,
implemented independently — it reproduces the house baseline's stated
practice loss of 0.387 exactly (0.3871 measured).

| Evaluation | This model | House baseline |
|---|---|---|
| Practice cases p00-p03 (mean) | **0.230** | 0.387 |
| LOO, big rolling launches, hour-1 >= 100k (n=19) | **0.209** | 0.262 |
| LOO, all rolling launches (n=29) | **0.201** | 0.282 |
| LOO, all 41 launches | 0.47 | 0.88 |

Per practice case: p00 Wolverine 0.373, p01 Red Dead Redemption 2 0.223,
p02 God of War Ragnarök 0.137, p03 Spider-Man 2 0.186. (Wolverine is the
hardest: a small hour 1 that grew 9.6x with a one-hour spike at hour 9
that no shape model can foresee.) Typical median miss on big rolling
launches is ~40% vs the baseline's ~56%; the 90% band covers ~0.90 of
scored hours in leave-one-out, i.e. the spread is honest, not padded.

## What could still beat us

The final is a single day. If GTA VI's hour 1 lands far outside the
range of past launches (e.g. above 3M), both components lean on the
biggest past launches and the evening median sits near 0.6-0.9x hour 1 —
the honest extrapolation of ELDEN RING / Cyberpunk 2077 behaviour. The
house AI-model forecast is the unknown: it was built from the same rules
and data, so it likely lands in the same region; this entry wins if its
median shape and honest spread are closer to the realised day than the
house's.
