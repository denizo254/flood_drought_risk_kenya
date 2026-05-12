"""Kenya Flood-Drought Risk Index — interactive Streamlit dashboard."""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent

st.set_page_config(
    page_title="Kenya Flood-Drought Risk Dashboard",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

RISK_COLORS = {"High": "#d73027", "Medium": "#f9a825", "Low": "#388e3c"}


def _simplify(coords, p=3):
    """Recursively round coordinate precision — reduces 7.9 MB GeoJSON ~70%."""
    if coords and isinstance(coords[0], (int, float)):
        return [round(c, p) for c in coords]
    return [_simplify(c, p) for c in coords]


@st.cache_data
def load_data():
    df = pd.read_csv(ROOT / "outputs" / "reports" / "county_risk_report.csv")
    with open(ROOT / "data" / "raw" / "kenya_counties.geojson") as f:
        geojson = json.load(f)
    for feat in geojson["features"]:
        feat["id"] = feat["properties"]["shapeName"]
        feat["geometry"]["coordinates"] = _simplify(feat["geometry"]["coordinates"])
    return df, geojson


def _minmax(series, val):
    mn, mx = series.min(), series.max()
    return float((val - mn) / (mx - mn)) if mx > mn else 0.0


def _norm_col(series):
    mn, mx = series.min(), series.max()
    return (series - mn) / (mx - mn) if mx > mn else series * 0.0


# ── Load ──────────────────────────────────────────────────────────────────────
df, geojson = load_data()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Kenya Risk Dashboard")
    st.caption("Flood & Drought Risk Index\nDecember 2025 analysis")
    st.divider()

    all_cats = sorted(df["risk_category"].dropna().unique())
    selected_cats = st.multiselect("Risk categories", all_cats, default=all_cats)
    st.divider()
    selected_county = st.selectbox("County spotlight", sorted(df["shapeName"]))

filtered = df[df["risk_category"].isin(selected_cats)]

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Kenya Flood-Drought Risk Index Dashboard")
st.caption(
    "Sources: CHIRPS v2.0 · MODIS MOD13A1 500 m · WorldPop 2020 · SRTM 90 m  |  "
    "Weights: rainfall 40 % · NDVI 30 % · population 20 % · slope 10 %"
)

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Counties", len(df))
k2.metric("High Risk", int((df["risk_category"] == "High").sum()))
k3.metric("Medium Risk", int((df["risk_category"] == "Medium").sum()))
k4.metric("Max Risk Index", f"{df['composite_risk_index'].max():.3f}")
k5.metric("Mean Risk Index", f"{df['composite_risk_index'].mean():.3f}")

st.divider()

# ── Choropleth map + ranking bar ───────────────────────────────────────────────
map_col, rank_col = st.columns([3, 2])

with map_col:
    map_df = filtered.copy()
    fig_map = px.choropleth_mapbox(
        map_df,
        geojson=geojson,
        featureidkey="id",
        locations="shapeName",
        color="composite_risk_index",
        hover_name="shapeName",
        hover_data={
            "composite_risk_index": ":.3f",
            "risk_category": True,
            "rainfall_zscore": ":.2f",
            "ndvi_deviation": ":.3f",
            "pop_density_norm": ":.3f",
        },
        color_continuous_scale="RdYlGn_r",
        range_color=(df["composite_risk_index"].min(), df["composite_risk_index"].max()),
        mapbox_style="carto-positron",
        zoom=5,
        center={"lat": 0.4, "lon": 37.9},
        opacity=0.75,
        height=520,
        title="Composite Risk Index by County",
        labels={"composite_risk_index": "Risk Index"},
    )
    fig_map.update_layout(
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        coloraxis_colorbar=dict(title="Risk Index", thickness=14, len=0.8),
    )
    st.plotly_chart(fig_map, use_container_width=True)

with rank_col:
    top_n = st.slider("Show top N counties", min_value=5, max_value=20, value=10)
    top = df.nlargest(top_n, "composite_risk_index")

    fig_bar = go.Figure(go.Bar(
        x=top["composite_risk_index"],
        y=top["shapeName"],
        orientation="h",
        marker_color=[RISK_COLORS.get(c, "#999") for c in top["risk_category"]],
        text=[f"{v:.3f}" for v in top["composite_risk_index"]],
        textposition="outside",
    ))
    fig_bar.update_layout(
        title=f"Top {top_n} Highest-Risk Counties",
        xaxis=dict(title="Composite Risk Index", range=[0, 1.08]),
        yaxis=dict(autorange="reversed"),
        height=520,
        margin={"r": 60, "t": 40, "l": 10, "b": 40},
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── County spotlight ──────────────────────────────────────────────────────────
st.divider()
st.subheader(f"County Spotlight: {selected_county}")

row = df[df["shapeName"] == selected_county].iloc[0]
cat_color = RISK_COLORS.get(str(row["risk_category"]), "#999")

# rank among all counties
rank = int(df["composite_risk_index"].rank(ascending=False)[df["shapeName"] == selected_county].iloc[0])
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Risk Index", f"{row['composite_risk_index']:.3f}", f"Rank {rank} / {len(df)}")
m2.metric("Category", row["risk_category"])
m3.metric("Rainfall Z-score", f"{row['rainfall_zscore']:.2f}")
m4.metric("NDVI Deviation", f"{row['ndvi_deviation']:.3f}")
m5.metric("Population (norm)", f"{row['pop_density_norm']:.3f}")

radar_col, scatter_col = st.columns(2)

with radar_col:
    r_vals = [
        _minmax(df["rainfall_zscore"], row["rainfall_zscore"]),
        1.0 - _minmax(df["ndvi_deviation"], row["ndvi_deviation"]),  # invert: lower = more drought
        float(row["pop_density_norm"]),
        float(row["slope_norm"]),
    ]
    r_labels = ["Rainfall Anomaly", "NDVI Drought Signal", "Population Exposure", "Terrain Slope"]

    fig_radar = go.Figure(go.Scatterpolar(
        r=r_vals + [r_vals[0]],
        theta=r_labels + [r_labels[0]],
        fill="toself",
        name=selected_county,
        line_color=cat_color,
    ))
    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title=f"Risk Profile — {selected_county}",
        height=400,
        margin={"t": 60, "b": 20},
    )
    st.plotly_chart(fig_radar, use_container_width=True)

with scatter_col:
    fig_scatter = px.scatter(
        df,
        x="rainfall_zscore",
        y="ndvi_deviation",
        color="risk_category",
        size="composite_risk_index",
        size_max=20,
        hover_name="shapeName",
        color_discrete_map=RISK_COLORS,
        title="Rainfall Anomaly vs NDVI Deviation",
        labels={"rainfall_zscore": "Rainfall Z-score (higher = more flood risk)",
                "ndvi_deviation": "NDVI Deviation (lower = more drought stress)"},
        height=400,
    )
    sel = df[df["shapeName"] == selected_county]
    fig_scatter.add_trace(go.Scatter(
        x=sel["rainfall_zscore"],
        y=sel["ndvi_deviation"],
        mode="markers+text",
        marker=dict(size=16, color="black", symbol="star"),
        text=[selected_county],
        textposition="top center",
        showlegend=False,
    ))
    st.plotly_chart(fig_scatter, use_container_width=True)

# ── Indicator heatmap ──────────────────────────────────────────────────────────
st.divider()
st.subheader("All-County Indicator Heatmap")
st.caption("Each indicator normalised 0–1 across all counties for comparison. "
           "NDVI deviation is inverted so red always means higher risk.")

heat_base = df.set_index("shapeName").sort_values("composite_risk_index", ascending=False)

heat_norm = pd.DataFrame({
    "Rainfall Anomaly":      _norm_col(heat_base["rainfall_zscore"]),
    "NDVI Drought Signal":   1.0 - _norm_col(heat_base["ndvi_deviation"]),
    "Population Exposure":   heat_base["pop_density_norm"],
    "Terrain Slope":         heat_base["slope_norm"],
    "Composite Risk Index":  _norm_col(heat_base["composite_risk_index"]),
})

fig_heat = px.imshow(
    heat_norm.T,
    color_continuous_scale="RdYlGn_r",
    zmin=0, zmax=1,
    aspect="auto",
    height=320,
    labels=dict(x="County (sorted by risk)", y="Indicator", color="Normalised value"),
)
fig_heat.update_xaxes(tickfont_size=8, tickangle=45)
fig_heat.update_layout(margin={"t": 20, "b": 80})
st.plotly_chart(fig_heat, use_container_width=True)

# ── Full data table ────────────────────────────────────────────────────────────
st.divider()
with st.expander("Full county data table", expanded=False):
    display = (
        filtered[["shapeName", "composite_risk_index", "risk_category",
                   "avg_rainfall_mm", "rainfall_zscore", "ndvi_deviation",
                   "pop_density_norm", "slope_norm"]]
        .sort_values("composite_risk_index", ascending=False)
        .rename(columns={
            "shapeName":             "County",
            "composite_risk_index":  "Risk Index",
            "risk_category":         "Category",
            "avg_rainfall_mm":       "Avg Rainfall (mm)",
            "rainfall_zscore":       "Rainfall Z-score",
            "ndvi_deviation":        "NDVI Deviation",
            "pop_density_norm":      "Pop. Density (norm)",
            "slope_norm":            "Slope (norm)",
        })
        .reset_index(drop=True)
    )
    st.dataframe(
        display.style.background_gradient(subset=["Risk Index"], cmap="RdYlGn_r"),
        use_container_width=True,
        hide_index=True,
    )
