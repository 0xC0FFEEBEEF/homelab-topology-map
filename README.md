# homelab-map

The lab topology page: four SVG diagrams (network map, slerm cluster, power-failure timeline, public edge)
drawn from the data at the top of `build.py`.

    python3 build.py    # writes the pages below
    ./render.sh         # also renders each poster to a 2x PNG with headless Chrome

| Output | Use |
|---|---|
| `homelab-map.html` | the page as an artifact |
| `site/nbdevlab-homelab.html` | the same page as a standalone document for nbdevlab.com |
| `poster-*.html`, `poster-*.png` | each diagram alone at its natural size |

This is the public version. It carries no addresses, port numbers, VM ids, software versions, tunnel or admin
hostnames, alert thresholds or auth details, and nothing work-related. `leak_check()` in `build.py` refuses to
write output that matches any of those patterns, so a new fact with an address fails the build.

The `SECURITY` and `CHANGES` lists in `build.py` are updated by hand.

## About this copy

A public snapshot of my private working repo. More of my projects: [nbdevlab.com](https://www.nbdevlab.com).


## About this copy

A public snapshot of my private working repo. More of my projects: [nbdevlab.com](https://www.nbdevlab.com).

## License

GNU General Public License v3.0 or later, see [`LICENSE`](LICENSE).

<sub>Preparing this public copy from my private repo was done with help from Claude.</sub>
