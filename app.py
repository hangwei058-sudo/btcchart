import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import json

st.set_page_config(
    page_title="Crypto & Gold Pro Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- 自定义 CSS 样式 -----------------
st.markdown("""
<style>
  /* 全局重置与深色背景 */
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .block-container {
    background: #0e1117 !important;
    color: #d1d4dc !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .block-container {
    padding: 0.2rem 0.5rem 0 !important;
    max-width: 100% !important;
  }
  [data-testid="stVerticalBlock"] {
    gap: 0.15rem !important;
  }
  header, footer {
    display: none !important;
  }

  /* 按钮扁平拟物化 & 交互微动效 */
  .stButton button {
    background: #1e222d !important;
    color: #9db2c6 !important;
    border: 1px solid #2a2e39 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    height: 32px !important;
    min-height: 32px !important;
    padding: 0 10px !important;
    border-radius: 6px !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
  }
  .stButton button:hover {
    background: #2a2e39 !important;
    color: #2962ff !important;
    border-color: #2962ff !important;
  }
  .stButton button:active {
    background: #2962ff !important;
    color: #fff !important;
    transform: scale(0.96) !important;
  }

  /* 下拉选择框深度美化 */
  [data-testid="stSelectbox"] > div > div {
    background: #1e222d !important;
    color: #fff !important;
    border: 1px solid #2a2e39 !important;
    border-radius: 6px !important;
    min-height: 32px !important;
    height: 32px !important;
  }
  [data-testid="stSelectbox"] > div > div > div {
    color: #f0f3fa !important;
    font-weight: 600 !important;
    font-size: 13px !important;
  }
  [data-testid="stSelectbox"] svg {
    fill: #787b86 !important;
  }

  /* 弹出菜单项美化 */
  div[data-baseweb="popover"] ul {
    background: #1e222d !important;
    border: 1px solid #2a2e39 !important;
    border-radius: 6px !important;
  }
  div[data-baseweb="popover"] li {
    background: #1e222d !important;
    color: #d1d4dc !important;
    font-size: 13px !important;
  }
  div[data-baseweb="popover"] li:hover {
    background: #2962ff !important;
    color: #ffffff !important;
  }
</style>
""", unsafe_allow_html=True)

SYMBOL_CONFIG = {"黄金 GOLD": "GC=F", "BTC/USDT": "BTC/USDT"}
TIME_CONFIG = {
    "7m":"7min","10m":"10min","15m":"15min","20m":"20min",
    "23m":"23min","30m":"30min","45m":"45min","90m":"90min",
    "1h":"1h","2h":"2h","3h":"3h","4h":"4h","6h":"6h",
    "8h":"8h","10h":"10h","12h":"12h","16h":"16h",
    "1d":"1D","2d":"2D","3d":"3D","4d":"4D","5d":"5D",
    "6d":"6D","7d":"7D","8d":"8D","9d":"9D","10d":"10D",
    "15d":"15D","20d":"20D","45d":"45D",
}
BAR_SECONDS = {
    "7m":420,"10m":600,"15m":900,"20m":1200,"23m":1380,
    "30m":1800,"45m":2700,"90m":5400,
    "1h":3600,"2h":7200,"3h":10800,"4h":14400,"6h":21600,
    "8h":28800,"10h":36000,"12h":43200,"16h":57600,
    "1d":86400,"2d":172800,"3d":259200,"4d":345600,"5d":432000,
    "6d":518400,"7d":604800,"8d":691200,"9d":777600,"10d":864000,
    "15d":1296000,"20d":1728000,"45d":3888000,
}
period_keys = list(TIME_CONFIG.keys())

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "1h"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "黄金 GOLD"

# ----------------- 顶部控制栏 -----------------
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([0.25, 0.25, 0.1, 0.4])

with ctrl_c1:
    is_gold = st.session_state.selected_symbol == "黄金 GOLD"
    if st.button("✦ 黄金 GOLD" if is_gold else "黄金 GOLD", key="g", use_container_width=True):
        st.session_state.selected_symbol = "黄金 GOLD"

with ctrl_c2:
    is_btc = st.session_state.selected_symbol == "BTC/USDT"
    if st.button("✦ BTC/USDT" if is_btc else "BTC/USDT", key="b", use_container_width=True):
        st.session_state.selected_symbol = "BTC/USDT"

with ctrl_c3:
    c_prev, c_next = st.columns(2)
    with c_prev:
        if st.button("◀", use_container_width=True):
            idx = period_keys.index(st.session_state.selected_label)
            st.session_state.selected_label = period_keys[(idx - 1) % len(period_keys)]
    with c_next:
        if st.button("▶", use_container_width=True):
            idx = period_keys.index(st.session_state.selected_label)
            st.session_state.selected_label = period_keys[(idx + 1) % len(period_keys)]

with ctrl_c4:
    new_label = st.selectbox(
        "周期选择",
        period_keys,
        index=period_keys.index(st.session_state.selected_label),
        label_visibility="collapsed"
    )
    st.session_state.selected_label = new_label

selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]
bar_seconds = BAR_SECONDS.get(selected_label, 3600)
is_btc_symbol = (symbol == "BTC/USDT")

BASE_FETCH_LIMIT = 50000

def get_base_interval(r_str):
    r = r_str.lower()
    if r.endswith('d'): return 'day'
    elif r.endswith('h'): return 'hour'
    return 'minute'

@st.cache_data(ttl=120)
def fetch_btc_1m(total_limit):
    exchange = ccxt.okx()
    per_call = 300
    all_bars = []
    since = exchange.milliseconds() - total_limit * 60 * 1000
    now = exchange.milliseconds()
    while since < now:
        try:
            bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1m', since=since, limit=per_call)
            if not bars: break
            all_bars += bars
            last_ts = bars[-1][0]
            if last_ts <= since: break
            since = last_ts + 60 * 1000
            if len(all_bars) >= total_limit: break
        except Exception:
            break
    return all_bars

@st.cache_data(ttl=120)
def get_btc_base_df():
    bars = fetch_btc_1m(BASE_FETCH_LIMIT)
    if not bars:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    return df[~df.index.duplicated(keep='last')].sort_index()

@st.cache_data(ttl=300)
def get_gold_df(base_type):
    ticker = yf.Ticker("GC=F")
    if base_type == 'minute':
        df = ticker.history(period="60d", interval="5m")
    elif base_type == 'hour':
        df = ticker.history(period="730d", interval="1h")
    else:
        df = ticker.history(period="10y", interval="1d")
    df = df[['Open','High','Low','Close','Volume']]
    df.columns = ['open','high','low','close','volume']
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    return df[~df.index.duplicated(keep='last')].sort_index()

@st.cache_data(ttl=120)
def resample_data(cur_symbol, cur_rule):
    base_type = get_base_interval(cur_rule)
    df = get_gold_df(base_type) if cur_symbol == "GC=F" else get_btc_base_df()
    if df.empty:
        return pd.DataFrame()
    resampled = df.resample(cur_rule).agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    ).dropna(subset=['open','high','low','close'])
    
    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd']   = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']
    resampled['ema24']  = resampled['close'].ewm(span=24, adjust=False).mean()
    resampled['ema52']  = resampled['close'].ewm(span=52, adjust=False).mean()
    resampled['ema104'] = resampled['close'].ewm(span=104, adjust=False).mean()
    return resampled.tail(2000)

df = resample_data(symbol, rule)

candles, ema24_data, ema52_data, ema104_data = [], [], [], []
macd_data, signal_data, hist_data = [], [], []
prev_h = None

if not df.empty:
    for idx, row in df.iterrows():
        t = int(idx.timestamp())
        candles.append({"time": t, "open": float(row['open']), "high": float(row['high']),
                        "low": float(row['low']), "close": float(row['close'])})
        if pd.notna(row['ema24']):  ema24_data.append({"time": t, "value": float(row['ema24'])})
        if pd.notna(row['ema52']):  ema52_data.append({"time": t, "value": float(row['ema52'])})
        if pd.notna(row['ema104']): ema104_data.append({"time": t, "value": float(row['ema104'])})
        if pd.notna(row['macd']):   macd_data.append({"time": t, "value": float(row['macd'])})
        if pd.notna(row['macd_s']): signal_data.append({"time": t, "value": float(row['macd_s'])})
        if pd.notna(row['macd_h']):
            v = float(row['macd_h'])
            if v >= 0:
                color = "#089981" if (prev_h is None or pd.isna(prev_h) or v >= prev_h) else "#26a69a80"
            else:
                color = "#f23645" if (prev_h is None or pd.isna(prev_h) or v <= prev_h) else "#f2364580"
            hist_data.append({"time": t, "value": v, "color": color})
            prev_h = v

last_price = candles[-1]['close'] if candles else 0.0
last_open  = candles[-1]['open']  if candles else 0.0
last_candle_time = candles[-1]['time'] if candles else 0

data_json = json.dumps({
    "candles": candles, "ema24": ema24_data, "ema52": ema52_data,
    "ema104": ema104_data, "macd": macd_data, "signal": signal_data, "hist": hist_data,
})

current_label_text = f"{selected_symbol_label} · {selected_label}"

html_content = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<script src="https://