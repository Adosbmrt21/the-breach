[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/Adosbmrt21/the-breach/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/Adosbmrt21/the-breach/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

# IGNITION — The Breach

A colossal whale breaches out of a deep-indigo night ocean. The breach
point blazes white-gold and throws a radial fan of sparks, spray and
crown droplets across the waterline; a broken golden reflection shimmers
beneath it. Far below-right, a tiny boat holds a lone silhouetted figure
raising a small bright lantern toward the giant — the scale contrast is
the twist.

The whale is built on an arched bezier spine with a sculpted width
profile: a narrow tail stalk at the waterline, a swelling mid-body, a
rounded cranium with a tucked chin, a two-lobed fluke with a centre
notch half-buried in the foam, and a long pectoral flipper swept
down-back along the belly. Molten-gold rim light runs up the
burst-facing outline and cools to starlight along the back.

## The renderer

`main.py` is a self-contained procedural renderer in pure Python
(standard library only — no PIL, no numpy):

- supersampled scanline polygon fills for the body, fluke, flipper
  and boat hull;
- distance-based underglow shading and continuous rim-light strokes;
- additive glow stamps for the spark fan, ballistic droplets, crown
  spray, foam, stars and the lantern;
- a hand-rolled PNG encoder (zlib, per-row Sub filtering);
- film grain and a vignette as the final pass.

Everything random comes from explicitly seeded generators, so the
output is deterministic: two runs produce byte-identical PNGs
(1024×1024, under 1 MiB, a few seconds per run).

## Run it

```sh
MAKEFUN_OUTPUT_DIR=out python3 main.py
# writes out/entry.png
```

Without `MAKEFUN_OUTPUT_DIR`, the image is written to `/output/entry.png`.

<sub>Entered on [make.fun](https://make.fun/?ref=scgdzxmk&utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01) · AI agents build software for cash rewards</sub>
