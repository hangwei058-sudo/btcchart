import streamlit as st
import ccxt
import pandas as pd
import time
from streamlit_lightweight_charts import renderLightweightCharts

st.set_page_config(layout="wide")

SYMBOL_CONFIG = {
    "BTC/USDT": "BTC/USDT",
    "黄金(PAXG/USDT)": "PAXG/USDT",
}

TIME_CONFIG = {
    "5m": "5min", "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "23m": "23min",
    "30m": "30min", "45m": "45min", "1h": "1h", "90m": "90min", "2h": "2h",
    "3h": "3h", "4h": "4h", "5h": "5h", "6h": "6h", "7h": "7h",
    "8h": "8h", "10h": "10h", "12h": "12h", "1d": "1d", "2d": "2d",
    "3d": "3d", "4d": "4d", "5d": "5d", "10d": "10d"
}

st.sidebar.title("品种选择")
selected_symbol_label = st.sidebar.selectbox("品种:", list(SYMBOL_CONFIG.keys()), index=0)
symbol = SYMBOL_CONFIG[selected_symbol_label]

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "15m"

st.write("时间级别：")
period_keys = list(TIME_CONFIG.keys())
n_cols = 7
for row_start in range(0, len(period_keys), n_cols):
    row_keys = period_keys[row_start:row_start + n_cols]
    cols = st.columns(n_cols)
    for i, key in enumerate(row_keys):
        is_active = (key == st.session_state.selected_label)
        label = f"●{key}" if is_active else key
        if cols[i].button(label, key=f"btn_{key}", use_container_width=True):
            st.session_state.selected_label = key

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

    # MACD
    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd'] = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']

    # EMA52
    resampled['ema52'] = resampled['close'].ewm(span=52, adjust=False).mean()

    # 标准 Stochastic（KD）：%K长度=5, %K平滑=3, %D平滑=3
    k_length, k_smooth, d_smooth = 5, 3, 3
    low_min = resampled['low'].rolling(k_length).min()
    high_max = resampled['high'].rolling(k_length).max()
    raw_k = (resampled['close'] - low_min) / (high_max - low_min) * 100
    resampled['stoch_k'] = raw_k.rolling(k_smooth).mean()
    resampled['stoch_d'] = resampled['stoch_k'].rolling(d_smooth).mean()

    return resampled.tail(2000)

df = resample_data(symbol, rule)
st.write(f"{selected_symbol_label} | 共加载 {len(df)} 条 {selected_label} K线")

candles = [
    {
        "time": int(idx.timestamp()),
        "open": float(row['open']), "high": float(row['high']),
        "low": float(row['low']), "close": float(row['close'])
    }
    for idx, row in df.iterrows()
]

ema52_line = [
    {"time": int(idx.timestamp()), "value": float(row['ema52'])}
    for idx, row in df.iterrows() if pd.notna(row['ema52'])
]

macd_line = [
    {"time": int(idx.timestamp()), "value": float(row['macd'])}
    for idx, row in df.iterrows() if pd.notna(row['macd'])
]
signal_line = [
    {"time": int(idx.timestamp()), "value": float(row['macd_s'])}
    for idx, row in df.iterrows() if pd.notna(row['macd_s'])
]

hist = []
prev_val = None
for idx, val in zip(df.index, df['macd_h'].values):
    if pd.isna(val):
        prev_val = val
        continue
    if val >= 0:
        color = "#26A69A" if (prev_val is None or pd.isna(prev_val) or val >= prev_val) else "#B2DFDB"
    else:
        color = "#FF5252" if (prev_val is None or pd.isna(prev_val) or val <= prev_val) else "#FFCDD2"
    hist.append({"time": int(idx.timestamp()), "value": float(val), "color": color})
    prev_val = val

stoch_k_line = [
    {"time": int(idx.timestamp()), "value": float(row['stoch_k'])}
    for idx, row in df.iterrows() if pd.notna(row['stoch_k'])
]
stoch_d_line = [
    {"time": int(idx.timestamp()), "value": float(row['stoch_d'])}
    for idx, row in df.iterrows() if pd.notna(row['stoch_d'])
]

chartOptions = {
    "height": 450,
    "layout": {"background": {"color": "#000000"}, "textColor": "white"},
    "grid": {"vertLines": {"color": "#222"}, "horzLines": {"color": "#222"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
}

macdChartOptions = {
    "height": 180,
    "layout": {"background": {"color": "#000000"}, "textColor": "white"},
    "grid": {"vertLines": {"color": "#222"}, "horzLines": {"color": "#222"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
}

stochChartOptions = {
    "height": 180,
    "layout": {"background": {"color": "#000000"}, "textColor": "white"},
    "grid": {"vertLines": {"color": "#222"}, "horzLines": {"color": "#222"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
}

seriesCandle = [
    {
        "type": 'Candlestick',
        "data": candles,
        "options": {
            "upColor": "#26A69A", "downColor": "#FF5252",
            "borderVisible": False,
            "wickUpColor": "#26A69A", "wickDownColor": "#FF5252"
        }
    },
    {
        "type": 'Line',
        "data": ema52_line,
        "options": {
            "color": "#FFD700", "lineWidth": 1,
            "lastValueVisible": False, "priceLineVisible": False
        }
    }
]

seriesMacd = [
    {"type": 'Histogram', "data": hist, "options": {
        "lastValueVisible": False, "priceLineVisible": False
    }},
    {"type": 'Line', "data": macd_line, "options": {
        "color": "blue", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
    {"type": 'Line', "data": signal_line, "options": {
        "color": "orange", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
]

seriesStoch = [
    {"type": 'Line', "data": stoch_k_line, "options": {
        "color": "blue", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
    {"type": 'Line', "data": stoch_d_line, "options": {
        "color": "orange", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
]

renderLightweightCharts([
    {"chart": chartOptions, "series": seriesCandle},
    {"chart": macdChartOptions, "series": seriesMacd},
    {"chart": stochChartOptions, "series": seriesStoch},
], 'multipane')