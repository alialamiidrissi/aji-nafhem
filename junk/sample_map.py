#!/usr/bin/env python3
"""
Sample geopolitical map generator — Middle East / Hormuz scenario.
Uses Natural Earth GeoJSON (fetched once, cached locally) + matplotlib.
No extra installs needed beyond matplotlib + requests.

Run:
  /Users/aalamiid/miniconda3/envs/audio_tts/bin/python junk/sample_map.py
"""

import json
import math
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no GUI window
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CACHE_FILE = Path(__file__).parent / "naturalearth_countries.geojson"
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)

OUTPUT_PNG = Path(__file__).parent / "sample_map.png"
OUTPUT_SVG = Path(__file__).parent / "sample_map.svg"

# Bounding box [lon_min, lat_min, lon_max, lat_max]
WEST, SOUTH, EAST, NORTH = 22, 10, 68, 43

HIGHLIGHT_COLORS = {
    "Iran":         "#C0392B",
    "Israel":       "#2980B9",
    "Saudi Arabia": "#E67E22",
    "Iraq":         "#8E44AD",
    "Yemen":        "#27AE60",
    "Lebanon":      "#16A085",
    "Syria":        "#95A5A6",
    "United Arab Emirates": "#F1C40F",
}

# Water / sea labels: text, (lon, lat, fontsize)
# Do NOT add an entry here if a MARKER already names the same place.
WATER_LABELS = {
    "Persian\nGulf":      (50.5, 27.5, 6.0),
    "Red Sea":            (36.5, 21.0, 6.0),
    "Mediterranean\nSea": (29.0, 33.5, 6.0),
    "Arabian\nSea":       (59.0, 16.5, 5.5),
    "Gulf of Aden":       (46.0, 12.5, 5.5),
}

# Point markers: (lon, lat, label, dot_color)
# Dot gets the accent color; label is always white-on-black for readability.
MARKERS = [
    (56.5, 26.5, "Strait of Hormuz", "#FFD700"),
    (34.8, 32.1, "Tel Aviv",         "#2980B9"),
    (51.4, 35.7, "Tehran",           "#C0392B"),
    (46.7, 24.7, "Riyadh",           "#E67E22"),
    (44.4, 33.3, "Baghdad",          "#8E44AD"),
]

# Proximity threshold (degrees) — if a placed label is within this distance,
# skip the new one to avoid duplicates / collisions.
LABEL_COLLISION_DEG = 3.0


# ---------------------------------------------------------------------------
# Geometry helpers (pure Python — no shapely required)
# ---------------------------------------------------------------------------

def _bbox_intersects(coords_flat, w, s, e, n):
    for lon, lat in coords_flat:
        if w <= lon <= e and s <= lat <= n:
            return True
    return False


def _flatten_coords(geometry):
    gtype = geometry["type"]
    coords = geometry["coordinates"]
    if gtype == "Point":
        yield tuple(coords[:2])
    elif gtype in ("MultiPoint", "LineString"):
        for c in coords:
            yield tuple(c[:2])
    elif gtype in ("Polygon", "MultiLineString"):
        for ring in coords:
            for c in ring:
                yield tuple(c[:2])
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for c in ring:
                    yield tuple(c[:2])


# ---------------------------------------------------------------------------
# Label collision tracker
# ---------------------------------------------------------------------------

class LabelTracker:
    """Tracks placed label positions and rejects new ones that are too close."""

    def __init__(self, min_dist_deg: float = LABEL_COLLISION_DEG):
        self._placed: list[tuple[float, float]] = []
        self._min_dist = min_dist_deg

    def try_place(self, x: float, y: float) -> bool:
        """Returns True and records the position if no collision, else False."""
        for px, py in self._placed:
            if math.hypot(x - px, y - py) < self._min_dist:
                return False
        self._placed.append((x, y))
        return True


# ---------------------------------------------------------------------------
# Shared text style helpers
# ---------------------------------------------------------------------------

# All readable labels: white fill + thick black stroke
_READABLE = [pe.withStroke(linewidth=3, foreground="black")]
# Water labels: light-blue italic + thick dark stroke
_WATER = [pe.withStroke(linewidth=3, foreground="#0D1B2A")]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_countries():
    if CACHE_FILE.exists():
        print(f"Loading cached Natural Earth data from {CACHE_FILE}")
        with open(CACHE_FILE) as f:
            return json.load(f)
    print("Downloading Natural Earth countries (~500 KB)...")
    r = requests.get(NE_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    CACHE_FILE.write_text(r.text)
    print(f"Cached to {CACHE_FILE}")
    return data


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_map():
    data = load_countries()
    tracker = LabelTracker()

    fig, ax = plt.subplots(figsize=(14, 9), facecolor="#0D1B2A")
    ax.set_facecolor("#1A3A5C")  # sea color
    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Countries ---
    for feat in data["features"]:
        name = feat["properties"].get("NAME", "") or feat["properties"].get("name", "")
        geom = feat["geometry"]
        if geom is None:
            continue

        flat = list(_flatten_coords(geom))
        if not _bbox_intersects(flat, WEST - 5, SOUTH - 5, EAST + 5, NORTH + 5):
            continue

        color      = HIGHLIGHT_COLORS.get(name, "#2C3E50")
        edge_color = "white" if name in HIGHLIGHT_COLORS else "#455A64"
        lw         = 1.0 if name in HIGHLIGHT_COLORS else 0.5
        alpha      = 0.9 if name in HIGHLIGHT_COLORS else 0.8

        polys = []
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            polys = geom["coordinates"]

        centroid_xs, centroid_ys = [], []
        for poly in polys:
            outer = poly[0]
            xs = [c[0] for c in outer]
            ys = [c[1] for c in outer]
            if not _bbox_intersects(list(zip(xs, ys)), WEST - 8, SOUTH - 8, EAST + 8, NORTH + 8):
                continue
            ax.fill(xs, ys, color=color, edgecolor=edge_color,
                    linewidth=lw, alpha=alpha, zorder=2)
            centroid_xs.append(sum(xs) / len(xs))
            centroid_ys.append(sum(ys) / len(ys))

        if name in HIGHLIGHT_COLORS and centroid_xs:
            cx = sum(centroid_xs) / len(centroid_xs)
            cy = sum(centroid_ys) / len(centroid_ys)
            if WEST < cx < EAST and SOUTH < cy < NORTH:
                if tracker.try_place(cx, cy):
                    ax.text(cx, cy, name,
                            fontsize=7, color="white", ha="center", va="center",
                            fontweight="bold", zorder=5,
                            path_effects=_READABLE)

    # --- Water labels ---
    for label, (x, y, fs) in WATER_LABELS.items():
        if tracker.try_place(x, y):
            ax.text(x, y, label,
                    fontsize=fs, color="#AED6F1", ha="center", va="center",
                    fontstyle="italic", zorder=4,
                    path_effects=_WATER)

    # --- Point markers ---
    # Dot uses the accent color; text is always white + black stroke.
    for lon, lat, label, dot_color in MARKERS:
        ax.plot(lon, lat, "o", ms=6, color=dot_color, zorder=6,
                markeredgecolor="white", markeredgewidth=0.8)
        if tracker.try_place(lon, lat):
            ax.text(lon + 1.0, lat, label,
                    fontsize=6.5, color="white", va="center", zorder=6,
                    fontweight="bold",
                    path_effects=_READABLE)

    # --- Hormuz strategic annotation (arrow only — label handled by MARKERS) ---
    ax.annotate("",
                xy=(56.5, 26.5), xytext=(54.8, 24.8),
                arrowprops=dict(arrowstyle="->", color="#FFD700", lw=1.8),
                zorder=7)

    # --- Legend ---
    handles = [mpatches.Patch(color=c, label=n)
               for n, c in HIGHLIGHT_COLORS.items()]
    ax.legend(handles=handles, loc="lower left", fontsize=7,
              framealpha=0.4, labelcolor="white",
              facecolor="#0D1B2A", edgecolor="#455A64")

    ax.set_title("Middle East — Strategic Overview (Hormuz Scenario)",
                 color="white", fontsize=13, fontweight="bold", pad=10)

    fig.tight_layout(pad=0.3)
    fig.savefig(OUTPUT_PNG, dpi=150, bbox_inches="tight")
    fig.savefig(OUTPUT_SVG, format="svg", bbox_inches="tight")
    print(f"Saved: {OUTPUT_PNG}")
    print(f"Saved: {OUTPUT_SVG}")
    subprocess.run(["open", str(OUTPUT_PNG)])


if __name__ == "__main__":
    render_map()
