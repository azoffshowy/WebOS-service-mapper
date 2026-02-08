# webOS ACG / Service Graphs

This repository contains:

- `site/` – static HTML graphs (D3) for different webOS versions
- `tools/mapEndpoints.py` – generator that scans `/usr/share/luna-service2` and emits an interactive HTML viewer

## Generate a graph

```bash
python3 tools/mapEndpoints.py \
  --base-dir /usr/share/luna-service2 \
  --output site/acg_webosXX_YY.ZZ.WW.html
