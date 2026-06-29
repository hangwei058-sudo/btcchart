import streamlit as st
import ccxt
import pandas as pd
import time
from streamlit_lightweight_charts import renderLightweightCharts

st.set_page_config(layout="wide")

TIME_CONFIG = {
    "5m": "5min", "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "30m": "30min", "45m": "45min", "1h": "1h", "90m": "90min", "2h": "2h",
    "3h": "3h", "4h": "4h", "5h": "5h", "6h": "6h", "7h": "7h",
    "8h": "8h", "10h": "10h", "12h": "12h", "1d": "1d", "2d": "2d",
    "3d": "3d", "10d": "10d"
}

st.sidebar.title("周期选择")
selected_label = st.sidebar.selectbox("选择:", list(TIME_CONFIG.keys()), index=3)
rule = TIME_CONFIG[selected_label]

MIN_BARS_NEEDED = 1000
PERIOD_MINUTES = {
    "5m": 5, "7m": 7, "10m": 10, "15m": 15, "20m": 20, "30m": 30, "45m": 45,
    "1h": 60, "90m": 90, "2h": 120, "3h": 180, "4h": 240, "5h": 300, "6h": 360,
    "7h": 420, "8h": 480, "10h": 600, "12h": 720, "1d": 1440, "2d": 2880,
    "3d": 4320, "10d": 14400
}

@st.cache_data(ttl=60)
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
        time.sleep(exchange.rateLimit / 1000)
        if len(all_bars) >= total_limit:
            break

    return all_bars

@st.cache_data(ttl=60)
def get_data(rule, label):
    minutes_per_bar = PERIOD_MINUTES[label]
    needed_minutes = (MIN_BARS_NEEDED + 50) * minutes_per_bar
    total_limit = max(needed_minutes, 6000)
    total_limit = min(total_limit, 100000)

    bars = fetch_all_ohlcv('BTC/USDT', '1m', total_limit)
    df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[~df.index.duplicated(keep='last')].sort_index()

    resampled = df.resample(rule).agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])

    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd'] = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']

    return resampled.tail(2000)

df = get_data(rule, selected_label)
st.write(f"共加载 {len(df)} 条 {selected_label} K线")

candles = [
    {
        "time": int(idx.timestamp()),
        "open": float(row['open']), "high": float(row['high']),
        "low": float(row['low']), "close": float(row['close'])
    }
    for idx, row in df.iterrows()
]

macd_line = [
    {"time": int(idx.timestamp()), "value": float(row['macd'])}
    for idx, row in df.iterrows() if pd.notna(row['macd'])
]
signal_line = [
    {"time": int(idx.timestamp()), "value": float(row['macd_s'])}
    for idx, row in df.iterrows() if pd.notna(row['macd_s'])
]

# 柱状图：根据涨跌+力度变化分深浅色，模仿TradingView效果
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

chartOptions = {
    "height": 500,
    "layout": {"background": {"color": "#000000"}, "textColor": "white"},
    "grid": {"vertLines": {"color": "#222"}, "horzLines": {"color": "#222"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
}

macdChartOptions = {
    "height": 200,
    "layout": {"background": {"color": "#000000"}, "textColor": "white"},
    "grid": {"vertLines": {"color": "#222"}, "horzLines": {"color": "#222"}},
    "timeScale": {"timeVisible": True, "secondsVisible": False},
}

seriesCandle = [{
    "type": 'Candlestick',
    "data": candles,
    "options": {
        "upColor": "#26A69A", "downColor": "#FF5252",
        "borderVisible": False,
        "wickUpColor": "#26A69A", "wickDownColor": "#FF5252"
    }
}]

seriesMacd = [
    {"type": 'Histogram', "data": hist, "options": {}},
    {"type": 'Line', "data": macd_line, "options": {
        "color": "blue", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
    {"type": 'Line', "data": signal_line, "options": {
        "color": "orange", "lineWidth": 1,
        "lastValueVisible": False, "priceLineVisible": False
    }},
]

renderLightweightCharts([
    {"chart": chartOptions, "series": seriesCandle},
    {"chart": macdChartOptions, "series": seriesMacd},
], 'multipane')
