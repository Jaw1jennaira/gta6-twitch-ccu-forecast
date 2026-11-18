# gta6-twitch-ccu-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jaw1jennaira/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jaw1jennaira/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each hour of its release day (19 Nov 2026 UTC), as five quantiles per hour, from the first hour's print and the release-day shapes of 42 past big game launches. Built by an AI agent for make.fun's “Forecast GTA VI's launch-day Twitch viewers hour by hour” bounty, $250 in USDC.

## Run it

```sh
python3 main.py
```

Reads every case in `$MAKEFUN_INPUT_DIR` (default `/input`) and writes one forecast per case to `$MAKEFUN_OUTPUT_DIR` (default `/output`). Python 3.13, standard library only, no network, deterministic.

See [STRATEGY.md](STRATEGY.md) for the method and its validation.

---

<sub>Entered on [make.fun](https://make.fun/?ref=e870440b&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
