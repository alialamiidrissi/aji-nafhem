"""
Map generator for the agentic video pipeline.

Takes a MapRequest schema object and renders an accurate geopolitical map
as a PNG using Natural Earth data + matplotlib. The PNG is placed in the
run's assets/ folder and loaded in Manim via ImageMobject.
"""

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no GUI window
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import requests

from agentic_video_gen.schemas import MapRequest

# ---------------------------------------------------------------------------
# Natural Earth data cache (shared across all runs)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "data"
_CACHE_FILE = _DATA_DIR / "naturalearth_countries.geojson"
_NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)

# Fixed output size — determines pixel_dimensions reported to Manim agent
_FIG_W_IN = 14.0   # inches
_FIG_H_IN = 9.0    # inches
_DPI = 150
PIXEL_WIDTH  = int(_FIG_W_IN * _DPI)   # 2100
PIXEL_HEIGHT = int(_FIG_H_IN * _DPI)   # 1350


def _load_countries() -> dict:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _CACHE_FILE.exists():
        with open(_CACHE_FILE) as f:
            return json.load(f)
    print("[map_gen] Downloading Natural Earth countries (~500 KB)...")
    r = requests.get(_NE_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    _CACHE_FILE.write_text(r.text)
    print(f"[map_gen] Cached to {_CACHE_FILE}")
    return data


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _bbox_intersects(coords_flat, w, s, e, n) -> bool:
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

class _LabelTracker:
    def __init__(self, min_dist_deg: float = 3.0):
        self._placed: list[tuple[float, float]] = []
        self._min = min_dist_deg

    def try_place(self, x: float, y: float) -> bool:
        for px, py in self._placed:
            if math.hypot(x - px, y - py) < self._min:
                return False
        self._placed.append((x, y))
        return True


# ---------------------------------------------------------------------------
# Shared text style
# ---------------------------------------------------------------------------
_READABLE = [pe.withStroke(linewidth=3, foreground="black")]
_WATER    = [pe.withStroke(linewidth=3, foreground="#0D1B2A")]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_map(request: MapRequest, output_path: Path) -> Path:
    """
    Render a geopolitical map PNG from a MapRequest.

    Args:
        request:     A MapRequest schema object describing what to draw.
        output_path: Full path where the PNG should be written.

    Returns:
        output_path (for chaining / logging).
    """
    west, south, east, north = request.bbox
    data     = _load_countries()
    tracker  = _LabelTracker()

    fig, ax = plt.subplots(figsize=(_FIG_W_IN, _FIG_H_IN), facecolor="#0D1B2A")
    ax.set_facecolor("#1A3A5C")   # sea
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_aspect("equal")
    ax.axis("off")

    highlight = request.highlight_countries  # dict: name → hex color

    # --- Countries ---
    for feat in data["features"]:
        name = feat["properties"].get("NAME", "") or feat["properties"].get("name", "")
        geom = feat["geometry"]
        if geom is None:
            continue

        flat = list(_flatten_coords(geom))
        if not _bbox_intersects(flat, west - 5, south - 5, east + 5, north + 5):
            continue

        color      = highlight.get(name, "#2C3E50")
        edge_color = "white" if name in highlight else "#455A64"
        lw         = 1.0    if name in highlight else 0.5
        alpha      = 0.9    if name in highlight else 0.8

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
            if not _bbox_intersects(
                list(zip(xs, ys)), west - 8, south - 8, east + 8, north + 8
            ):
                continue
            ax.fill(xs, ys, color=color, edgecolor=edge_color,
                    linewidth=lw, alpha=alpha, zorder=2)
            centroid_xs.append(sum(xs) / len(xs))
            centroid_ys.append(sum(ys) / len(ys))

        if name in highlight and centroid_xs:
            cx = sum(centroid_xs) / len(centroid_xs)
            cy = sum(centroid_ys) / len(centroid_ys)
            if west < cx < east and south < cy < north:
                if tracker.try_place(cx, cy):
                    ax.text(cx, cy, name,
                            fontsize=7, color="white", ha="center", va="center",
                            fontweight="bold", zorder=5,
                            path_effects=_READABLE)

    # --- Water labels ---
    for label, coords in request.water_labels.items():
        if not coords:
            print(f"[map_gen] Skipping water label '{label}' — coords is None/empty")
            continue
        lon, lat = coords[0], coords[1]
        if tracker.try_place(lon, lat):
            ax.text(lon, lat, label,
                    fontsize=6.0, color="#AED6F1", ha="center", va="center",
                    fontstyle="italic", zorder=4,
                    path_effects=_WATER)

    # --- Point markers (skip any that fall outside the bbox) ---
    for marker in request.markers:
        if not (west <= marker.lon <= east and south <= marker.lat <= north):
            print(f"[map_gen] Skipping out-of-bbox marker '{marker.label}' ({marker.lon}, {marker.lat})")
            continue
        ax.plot(marker.lon, marker.lat, "o", ms=6,
                color=marker.dot_color, zorder=6,
                markeredgecolor="white", markeredgewidth=0.8)
        if tracker.try_place(marker.lon, marker.lat):
            ax.text(marker.lon + 1.0, marker.lat, marker.label,
                    fontsize=6.5, color="white", va="center",
                    fontweight="bold", zorder=6,
                    path_effects=_READABLE)

    # --- Legend (only for highlighted countries) ---
    if highlight:
        handles = [mpatches.Patch(color=c, label=n) for n, c in highlight.items()]
        ax.legend(handles=handles, loc="lower left", fontsize=7,
                  framealpha=0.4, labelcolor="white",
                  facecolor="#0D1B2A", edgecolor="#455A64")

    if request.title:
        ax.set_title(request.title, color="white",
                     fontsize=13, fontweight="bold", pad=10)

    fig.tight_layout(pad=0.3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[map_gen] Saved {output_path}  ({PIXEL_WIDTH}×{PIXEL_HEIGHT}px)")
    return output_path
