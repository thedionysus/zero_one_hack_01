# Bake-off results

Winner per fertilizer = lowest MASE (tiebreak MAPE), scored from
backtest_trajectories.json with stale windows excluded. MASE/RMSSE < 1
means the config beats a lag-12 seasonal-naive baseline.

| fertilizer | winner | MASE | RMSSE | MAPE% | cov80 | cov90 | beats naive? |
|---|---|---|---|---|---|---|---|
| urea | OFF | 1.10 | 0.80 | 20.8 | 21% | 33% | no |
| dap | OFF | 1.18 | 0.78 | 17.1 | 21% | 29% | no |
| mop | ON | 0.63 | 0.31 | 16.0 | 50% | 58% | YES |
| tsp | OFF | 1.22 | 0.76 | 21.4 | 21% | 38% | no |
| phosphate-rock | OFF | 0.62 | 0.44 | 18.3 | 100% | 100% | YES |

## Per-variant detail

### urea (winner: OFF) (TIE — OFF chosen, all variants equal) (forward bands: NATIVE)
- ON: MASE 1.10, MAPE 20.8%, cov80 21%, 11 stale windows excluded
- MID: MASE 1.10, MAPE 20.8%, cov80 21%, 11 stale windows excluded
- OFF: MASE 1.10, MAPE 20.8%, cov80 21%, 11 stale windows excluded
### dap (winner: OFF) (TIE — OFF chosen, all variants equal) (forward bands: NATIVE)
- ON: MASE 1.18, MAPE 17.1%, cov80 21%, 11 stale windows excluded
- MID: MASE 1.18, MAPE 17.1%, cov80 21%, 11 stale windows excluded
- OFF: MASE 1.18, MAPE 17.1%, cov80 21%, 11 stale windows excluded
### mop (winner: ON) (forward bands: MISSING — derive from hindcast)
- ON: MASE 0.63, MAPE 16.0%, cov80 50%, 11 stale windows excluded
- MID: MASE 0.66, MAPE 16.8%, cov80 33%, 11 stale windows excluded
- OFF: MASE 0.68, MAPE 17.1%, cov80 29%, 11 stale windows excluded
### tsp (winner: OFF) (forward bands: MISSING — derive from hindcast)
- OFF: MASE 1.22, MAPE 21.4%, cov80 21%, 11 stale windows excluded
- MID: MASE 1.40, MAPE 24.6%, cov80 0%, 11 stale windows excluded
- ON: MASE 1.40, MAPE 24.7%, cov80 4%, 11 stale windows excluded
### phosphate-rock (winner: OFF) (forward bands: MISSING — derive from hindcast)
- OFF: MASE 0.62, MAPE 18.3%, cov80 100%, 11 stale windows excluded
- ON: MASE 2.10, MAPE 61.7%, cov80 100%, 11 stale windows excluded
- MID: MASE 2.10, MAPE 61.7%, cov80 100%, 11 stale windows excluded
