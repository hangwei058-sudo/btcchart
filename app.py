import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import time
import json

st.set_page_config(layout="wide")

SYMBOL_CONFIG = {
    "BTC/USDT": "BTC/USDT",
    "黄金 GOLD": "GC=F",
}

TIME_CONFIG = {
    "5m": "5min", "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "23m": "23min", "30m": "30min", "45m": "45min",
    "1h": "1h", "90m": "90min", "2h": "2h", "3h": "3h", "4h": "4h",
    "5h": "5h", "6h": "6h", "7h": "7h", "8h": "8h", "9h": "9h",
    "10h": "10h", "12h": "12h", "16h": "16h", "18h": "18h",
    "1d": "1D", "2d": "2D", "3d": "3D", "4d": "4D", "5d": "5D",
    "6d": "6D", "7d": "7D", "8d": "8D", "9d": "9D", "10d": "10D",
    "15d": "15D", "20d": "20D", "30d": "30D", "45d": "45D",
}

period_keys = list(TIME_CONFIG.keys())

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "15m"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "BTC/USDT"

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

def get_base_interval(rule):
    """根据重采样周期，决定用哪种基础数据粒度"""
    r = rule.lower()
    if r.endswith('d'):  # 天级
        return 'day'
    elif r.endswith('h'):
        mins = int(r[:-1]) * 60
        return 'hour'
    elif r.endswith('min'):
        mins = int(r[:-3])
        return 'minute'
    return 'hour'

BASE_FETCH_LIMIT = 50000

@st.cache_data(ttl=120)
def fetch_btc_1m(total_limit):
    exchange = ccxt.okx()
    per_call = 300
    all_bars = []
    since = exchange.milliseconds() - total_limit * 60 * 1000
    now = exchange.milliseconds()
    while since < now:
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1m', since=since, limit=per_call)
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
def get_btc_base_df():
    bars = fetch_btc_1m(BASE_FETCH_LIMIT)
    df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[~df.index.duplicated(keep='last')].sort_index()
    return df

@st.cache_data(ttl=300)
def get_gold_df(base_type):
    """用 yfinance 拉黄金数据，按需选择粒度"""
    if base_type == 'minute':
        # 5m数据，最多60天
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="60d", interval="5m")
    elif base_type == 'hour':
        # 1h数据，最多730天
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="730d", interval="1h")
    else:
        # 1d数据，拉10年
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="10y", interval="1d")

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    df = df[~df.index.duplicated(keep='last')].sort_index()
    return df

@st.cache_data(ttl=120)
def resample_data(symbol, rule):
    base_type = get_base_interval(rule)

    if symbol == "GC=F":
        df = get_gold_df(base_type)
    else:
        df = get_btc_base_df()

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
    "candles": candles, "ema52": ema52_data, "macd": macd_data,
    "signal": signal_data, "hist": hist_data,
    "stoch_k": stoch_k_data, "stoch_d": stoch_d_data,
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

const commonLocalization = {{
  timeFormatter: timestamp => {{
    const d = new Date(timestamp * 1000);
    const myt = new Date(d.getTime() + 8 * 60 * 60 * 1000);
    const mo = String(myt.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(myt.getUTCDate()).padStart(2, '0');
    const hh = String(myt.getUTCHours()).padStart(2, '0');
    const min = String(myt.getUTCMinutes()).padStart(2, '0');
    return mo + '/' + dd + ' ' + hh + ':' + min;
  }}
}};

const w = window.innerWidth;
const h = window.innerHeight;

const chart1 = LightweightCharts.createChart(document.getElementById('chart1'), {{
  width: w, height: Math.floor(h * 0.42),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  localization: commonLocalization,
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
  crosshairMarkerVisible: false,
}});
ema52Series.setData(data.ema52);

const chart2 = LightweightCharts.createChart(document.getElementById('chart2'), {{
  width: w, height: Math.floor(h * 0.20),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  localization: commonLocalization,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#333' }},
}});
const histSeries = chart2.addHistogramSeries({{
  lastValueVisible: false, priceLineVisible: false,
  crosshairMarkerVisible: false,
}});
histSeries.setData(data.hist);
const macdSeries = chart2.addLineSeries({{
  color: '#2962FF', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
  crosshairMarkerVisible: false,
}});
macdSeries.setData(data.macd);
const signalSeries = chart2.addLineSeries({{
  color: '#FF6D00', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
  crosshairMarkerVisible: false,
}});
signalSeries.setData(data.signal);

const chart3 = LightweightCharts.createChart(document.getElementById('chart3'), {{
  width: w, height: Math.floor(h * 0.15),
  layout: commonLayout, grid: commonGrid, timeScale: commonTimeScale,
  localization: commonLocalization,
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#333' }},
}});
const stochKSeries = chart3.addLineSeries({{
  color: '#2962FF', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
  crosshairMarkerVisible: false,
}});
stochKSeries.setData(data.stoch_k);
const stochDSeries = chart3.addLineSeries({{
  color: '#FF6D00', lineWidth: 1,
  lastValueVisible: false, priceLineVisible: false,
  crosshairMarkerVisible: false,
}});
stochDSeries.setData(data.stoch_d);

[20, 50, 80].forEach(level => {{
  stochKSeries.createPriceLine({{
    price: level, color: '#888888', lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true, title: '',
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

st.components.v1.html(html, height=850, scrolling=False)