import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import geopandas as gpd
from pathlib import Path

_CATEGORY_COLORS = {"Low": "#2196F3", "Medium": "#FFC107", "High": "#F44336"}
_ATTRIBUTION = "Data: CHIRPS v2.0 | Boundaries: geoBoundaries | Author: Laono Denis"


def plot_risk_map(gdf: gpd.GeoDataFrame, config: dict) -> Path:
    cols = config["columns"]
    maps_dir = Path(config["paths"]["maps"])
    maps_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    fig.suptitle(
        "Kenya Flood–Drought Risk Assessment",
        fontsize=20, fontweight="bold", y=0.98,
    )

    # Left panel: Rainfall Z-score
    ax1 = axes[0]
    gdf.plot(
        column=cols["rainfall_zscore"],
        cmap="RdYlBu",
        linewidth=0.5,
        ax=ax1,
        edgecolor="0.3",
        legend=True,
        legend_kwds={
            "label": "Rainfall Z-Score (Dec 2025)",
            "orientation": "horizontal",
            "shrink": 0.7,
            "pad": 0.05,
        },
        missing_kwds={"color": "lightgrey", "label": "No data"},
    )
    ax1.set_title("Rainfall Anomaly (Z-Score)", fontsize=14, pad=10)
    ax1.set_axis_off()

    # Right panel: Composite Risk Index
    ax2 = axes[1]
    cat_col = cols["risk_category"]
    if cat_col in gdf.columns and gdf[cat_col].notna().any():
        gdf["_color"] = gdf[cat_col].map(_CATEGORY_COLORS).fillna("#CCCCCC")
        gdf.plot(color=gdf["_color"], linewidth=0.5, ax=ax2, edgecolor="0.3")
        gdf.drop(columns=["_color"], inplace=True)
        patches = [mpatches.Patch(color=c, label=lbl) for lbl, c in _CATEGORY_COLORS.items()]
        ax2.legend(handles=patches, loc="lower left", fontsize=11, title="Risk Level")
    else:
        gdf.plot(
            column=cols["risk_index"],
            cmap="YlOrRd",
            linewidth=0.5,
            ax=ax2,
            edgecolor="0.3",
            legend=True,
            legend_kwds={
                "label": "Composite Risk Index (0–1)",
                "orientation": "horizontal",
                "shrink": 0.7,
                "pad": 0.05,
            },
        )
    ax2.set_title("Composite Risk Index", fontsize=14, pad=10)
    ax2.set_axis_off()

    plt.annotate(
        _ATTRIBUTION,
        xy=(0.5, 0.02), xycoords="figure fraction",
        ha="center", fontsize=9, color="gray",
    )

    output_path = maps_dir / "kenya_risk_map.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  [OK] Risk map saved: {output_path}")
    return output_path


def plot_county_ranking(gdf: gpd.GeoDataFrame, config: dict, top_n: int = 15) -> Path:
    cols = config["columns"]
    maps_dir = Path(config["paths"]["maps"])
    maps_dir.mkdir(parents=True, exist_ok=True)

    top = gdf.nlargest(top_n, cols["risk_index"]).copy()

    cat_col = cols["risk_category"]
    if cat_col in top.columns:
        colors = top[cat_col].map(_CATEGORY_COLORS).fillna("#CCCCCC").tolist()
    else:
        colors = "#607D8B"

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top[cols["county_name"]], top[cols["risk_index"]], color=colors)
    ax.set_xlabel("Composite Risk Index (0–1)", fontsize=12)
    ax.set_title(f"Top {top_n} Highest-Risk Counties — Kenya", fontsize=14, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.axvline(
        x=config["risk_categories"]["high"],
        color="red", linestyle="--", alpha=0.6, label="High threshold",
    )
    ax.axvline(
        x=config["risk_categories"]["medium"],
        color="orange", linestyle="--", alpha=0.6, label="Medium threshold",
    )
    ax.legend(fontsize=10)
    plt.tight_layout()

    output_path = maps_dir / "county_risk_ranking.png"
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  [OK] County ranking chart saved: {output_path}")
    return output_path
