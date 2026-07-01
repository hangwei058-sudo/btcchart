import streamlit as st
import ccxt
import pandas as pd
import time
import json

st.set_page_config(layout="wide")

SYMBOL_CONFIG = {
    "BTC/USDT": "BTC/USDT",
    "黄金(PAXG/USDT)": "PAXG/USDT",
}

TIME_CONFIG = {
    "5m": "5min", "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "23m": "23min", "30m": "30min", "45m": "45min", "1h": "1h", "90m": "90min",
    "2h": "2h", "3h": "3h", "4h": "4h", "5h": "5h", "6h": "6h", "7h": "7h",
    "8h": "8h", "10h": "10h", "12h": "12h", "1d": "1d", "2d": "2d",
    "3d": "3d", "4d": "4d", "5d": "5d", "10d": "10d"
}

period_keys = list(TIME_CONFIG.keys())

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "15m"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "BTC/USDT"

# 顶部一行：品种 | 周期下拉 | ◀ | ▶
col1, col2, col3, col4 = st.columns([1.5, 1.5, 0.5, 0.5])

with col1:
    selected_symbol_label = st.selectbox(
        "品种", list(SYMBOL_CONFIG.keys()),
        index=list(SYMBOL_CONFIG.keys()).index(st.session_state.selected_symbol)
        if st.session_state.selected_symbol in SYMBOL_CONFIG else 0,
        label_visibility="collapsed"
    )
    st.session_state.selected_symbol = selected_symbol_label
    symbol = SYMBOL_CONFIG[selected_symbol_label]

with col2:
    new_label = st.selectbox(
        "周期", period_keys,
        index=period_keys.index(st.session_state.selected_label),
        label_visibility="collapsed"
    )
    st.session_state.selected_label = new_label

with col3:
    if st.button("◀", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx - 1) % len(period_keys)]

with col4:
    if st.button("▶", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx + 1) % len(period_keys)]

selected_label = st.session_state.selected_label
rule = TIME_CONFIG[selected_label]

BASE_FETCH_LIMIT = 50000

@st.cache_data(ttl=120)
def fetch_all_ohlcv(symbol, timeframe, total_limit):
    exchange = ccxt.okx()
    per_call = 300
    all_bars = []
    since = exchange.milliseconds() - total_limit * 60 * 1000
    now = exchange.milliseconds()
    while since < now:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=per_call)
        if not bars:
            break
        all_bars += bars
        last_ts = bars[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 60 * 1000
        if len(all_bars) >= total_limit:
            break
    return all_bars

@st.cache_data(ttl=120)
def get_base_df(symbol):
    bars = fetch_all_ohlcv(symbol, '1m', BASE_FETCH_LIMIT)
    df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[~df.index.duplicated(keep='last')].sort_index()
    return df

@st.cache_data(ttl=120)
def resample_data(symbol, rule):
    df = get_base_df(symbol)
    resampled = df.resample(rule).agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])

    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd'] = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']

    resampled['ema52'] = resampled['close'].ewm(span=52, adjust=False).mean()

    k_length, k_smooth, d_smooth = 5, 3, 3
    low_min = resampled['low'].rolling(k_length).min()
    high_max = resampled['high'].rolling(k_length).max()
    raw_k = (resampled['close'] - low_min) / (high_max - low_min) * 100
    resampled['stoch_k'] = raw_k.rolling(k_smooth).mean()
    resampled['stoch_d'] = resampled['stoch_k'].rolling(d_smooth).mean()

    return resampled.tail(2000)

df = resample_data(symbol, rule)
st.write(f"{selected_symbol_label} | 共加载 {len(df)} 条 {selected_label} K线")

candles, ema52_data, macd_data, signal_data, hist_data, stoch_k_data, stoch_d_data = [], [], [], [], [], [], []

prev_h = None
for idx, row in df.iterrows():
    t = int(idx.timestamp())
    candles.append({"time": t, "open": float(row['open']), "high": float(row['high']),
                    "low": float(row['low']), "close": float(row['close'])})
    if pd.notna(row['ema52']):
        ema52_data.append({"time": t, "value": float(row['ema52'])})
    if pd.notna(row['macd']):
        macd_data.append({"time": t, "value": float(row['macd'])})
    if pd.notna(row['macd_s']):
        signal_data.append({"time": t, "value": float(row['macd_s'])})
    if pd.notna(row['macd_h']):
        v = float(row['macd_h'])
        if v >= 0:
            color = "#26A69A" if (prev_h is None or pd.isna(prev_h) or v >= prev_h) else "#B2DFDB"
        else:
            color = "#FF5252" if (prev_h is None or pd.isna(prev_h) or v <= prev_h) else "#FFCDD2"
        hist_data.append({"time": t, "value": v, "color": color})
        prev_h = v
    if pd.notna(row['stoch_k']):
        stoch_k_data.append({"time": t, "value": float(row['stoch_k'])})
    if pd.notna(row['stoch_d']):
        stoch_d_data.append({"time": t, "value": float(row['stoch_d'])})

data_json = json.dumps({
    "candles": candles,
    "ema52": ema52_data,
    "macd": macd_data,
    "signal": signal_data,
    "hist": hist_data,
    "stoch_k": stoch_k_data,
    "stoch_d": stoch_d_data,
})

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; background: #000; }}
  #chart1, #chart2, #chart3 {{ width: 100%; }}
</style>
</head>
<body>
<div id="chart1"></div>
<div id="chart2"></div>
<div id="chart3"></div>
<script>
const data = {data_json};

const commonLayout = {{ background: {{ color: '#000000' }}, textColor: 'white' }};
const commonGrid = {{ vertLines: {{ color: '#222' }}, horzLines: {{ color: '#222' }} }};
const commonTimeScale = {{ timeVisible: true, secondsVisible: false, borderColor: '#333' }};

const w = window.innerWidth;
const h = window.innerHeight;

const chart1 = LightweightCharts.createChart(document.getElementById('chart1'), {{
  width: w, height: Math.floor(h * 0.52),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#333' }},
}});
const candleSeries = chart1.addCandlestickSeries({{
  upColor: '#26A69A', downColor: '#FF5252',
  borderVisible: false,
  wickUpColor: '#26A69A', wickDownColor: '#FF5252',
}});
candleSeries.setData(data.candles);
const ema52Series = chart1.addLineSeries({{
  color: '#FFD700', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
}});
ema52Series.setData(data.ema52);

const chart2 = LightweightCharts.createChart(document.getElementById('chart2'), {{
  width: w, height: Math.floor(h * 0.25),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#333' }},
}});
const histSeries = chart2.addHistogramSeries({{
  lastValueVisible: false, priceLineVisible: false,
}});
histSeries.setData(data.hist);
const macdSeries = chart2.addLineSeries({{
  color: '#2962FF', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
}});
macdSeries.setData(data.macd);
const signalSeries = chart2.addLineSeries({{
  color: '#FF6D00', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
}});
signalSeries.setData(data.signal);

const chart3 = LightweightCharts.createChart(document.getElementById('chart3'), {{
  width: w, height: Math.floor(h * 0.18),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#333' }},
}});
const stochKSeries = chart3.addLineSeries({{
  color: '#2962FF', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
}});
stochKSeries.setData(data.stoch_k);
const stochDSeries = chart3.addLineSeries({{
  color: '#FF6D00', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
}});
stochDSeries.setData(data.stoch_d);

[20, 50, 80].forEach(level => {{
  stochKSeries.createPriceLine({{
    price: level,
    color: '#888888',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: '',
  }});
}});

const chartSeriesPairs = [
  [chart1, candleSeries],
  [chart2, histSeries],
  [chart3, stochKSeries],
];

let isSyncing = false;

chartSeriesPairs.forEach(([sourceChart, sourceSeries]) => {{
  sourceChart.subscribeCrosshairMove(param => {{
    if (isSyncing) return;
    isSyncing = true;
    chartSeriesPairs.forEach(([targetChart, targetSeries]) => {{
      if (targetChart === sourceChart) return;
      if (param.time) {{
        const price = targetSeries.coordinateToPrice(param.point ? param.point.y : 0);
        targetChart.setCrosshairPosition(price ?? 0, param.time, targetSeries);
      }} else {{
        targetChart.clearCrosshairPosition();
      }}
    }});
    isSyncing = false;
  }});
}});

chartSeriesPairs.forEach(([sourceChart]) => {{
  sourceChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
    if (isSyncing || !range) return;
    isSyncing = true;
    chartSeriesPairs.forEach(([targetChart]) => {{
      if (targetChart !== sourceChart) {{
        targetChart.timeScale().setVisibleLogicalRange(range);
      }}
    }});
    isSyncing = false;
  }});
}});

window.addEventListener('resize', () => {{
  chartSeriesPairs.forEach(([c]) => c.applyOptions({{ width: window.innerWidth }}));
}});
</script>
</body>
</html>
"""

st.components.v1.html(html, height=950, scrolling=False)