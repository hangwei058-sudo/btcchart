import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import json

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# 隐藏 Streamlit 默认 padding，最大化图表空间
st.markdown("""
<style>
  .block-container { padding-top: 0.3rem !important; padding-bottom: 0 !important; }
  div[data-testid="stVerticalBlock"] { gap: 0.2rem; }
  header { display: none !important; }
</style>
""", unsafe_allow_html=True)

SYMBOL_CONFIG = {
    "黄金 GOLD": "GC=F",
    "BTC/USDT": "BTC/USDT",
}

TIME_CONFIG = {
    "7m": "7min", "10m": "10min", "15m": "15min", "20m": "20min",
    "23m": "23min", "30m": "30min", "45m": "45min", "90m": "90min",
    "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h",
    "8h": "8h", "10h": "10h", "12h": "12h", "16h": "16h",
    "1d": "1D", "2d": "2D", "3d": "3D", "4d": "4D", "5d": "5D",
    "6d": "6D", "7d": "7D", "8d": "8D", "9d": "9D", "10d": "10D",
    "15d": "15D", "20d": "20D", "45d": "45D",
}

period_keys = list(TIME_CONFIG.keys())

if "selected_label" not in st.session_state:
    st.session_state.selected_label = "1h"
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "黄金 GOLD"

# 极简顶部控制栏：一行搞定
c1, c2, c3, c4 = st.columns([1.2, 1.8, 0.5, 0.5])

with c1:
    sym = st.selectbox("品种", list(SYMBOL_CONFIG.keys()),
                       index=list(SYMBOL_CONFIG.keys()).index(st.session_state.selected_symbol),
                       label_visibility="collapsed")
    st.session_state.selected_symbol = sym

with c2:
    period = st.selectbox("周期", period_keys,
                          index=period_keys.index(st.session_state.selected_label),
                          label_visibility="collapsed")
    st.session_state.selected_label = period

with c3:
    if st.button("◀", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx - 1) % len(period_keys)]

with c4:
    if st.button("▶", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx + 1) % len(period_keys)]

selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]

BASE_FETCH_LIMIT = 50000

def get_base_interval(rule):
    r = rule.lower()
    if r.endswith('d'):
        return 'day'
    elif r.endswith('h'):
        return 'hour'
    return 'minute'

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
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    return df[~df.index.duplicated(keep='last')].sort_index()

@st.cache_data(ttl=120)
def resample_data(symbol, rule):
    base_type = get_base_interval(rule)
    df = get_gold_df(base_type) if symbol == "GC=F" else get_btc_base_df()

    resampled = df.resample(rule).agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    ).dropna(subset=['open', 'high', 'low', 'close'])

    ema12 = resampled['close'].ewm(span=12, adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26, adjust=False).mean()
    resampled['macd'] = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9, adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']
    resampled['ema24']  = resampled['close'].ewm(span=24,  adjust=False).mean()
    resampled['ema52']  = resampled['close'].ewm(span=52,  adjust=False).mean()
    resampled['ema104'] = resampled['close'].ewm(span=104, adjust=False).mean()

    return resampled.tail(2000)

df = resample_data(symbol, rule)

candles = []
ema24_data, ema52_data, ema104_data = [], [], []
macd_data, signal_data, hist_data = [], [], []
prev_h = None

for idx, row in df.iterrows():
    t = int(idx.timestamp())
    candles.append({"time": t, "open": float(row['open']), "high": float(row['high']),
                    "low": float(row['low']), "close": float(row['close'])})
    if pd.notna(row['ema24']):
        ema24_data.append({"time": t, "value": float(row['ema24'])})
    if pd.notna(row['ema52']):
        ema52_data.append({"time": t, "value": float(row['ema52'])})
    if pd.notna(row['ema104']):
        ema104_data.append({"time": t, "value": float(row['ema104'])})
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

data_json = json.dumps({
    "candles": candles, "ema24": ema24_data, "ema52": ema52_data,
    "ema104": ema104_data, "macd": macd_data, "signal": signal_data, "hist": hist_data,
})

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: #000; overflow: hidden; }}
  #chart1, #chart2 {{ width: 100%; }}
  #label {{ color:#aaa; font-size:11px; font-family:sans-serif;
            padding:2px 6px; background:#000; }}
</style>
</head>
<body>
<div id="label">{selected_symbol_label} · {selected_label} · {len(df)} 条K线</div>
<div id="chart1"></div>
<div id="chart2"></div>
<script>
const data = {data_json};
const commonLayout = {{ background:{{color:'#000'}}, textColor:'white' }};
const commonGrid   = {{ vertLines:{{color:'#222'}}, horzLines:{{color:'#222'}} }};
const commonTS     = {{ timeVisible:true, secondsVisible:false, borderColor:'#333' }};
const commonLoc    = {{ timeFormatter: ts => {{
  const d = new Date(ts*1000 + 8*3600*1000);
  const mo  = String(d.getUTCMonth()+1).padStart(2,'0');
  const dd  = String(d.getUTCDate()).padStart(2,'0');
  const hh  = String(d.getUTCHours()).padStart(2,'0');
  const min = String(d.getUTCMinutes()).padStart(2,'0');
  return mo+'/'+dd+' '+hh+':'+min;
}} }};

const W = window.innerWidth;
const H = window.innerHeight - 20;
const H1 = Math.floor(H * 0.65);
const H2 = Math.floor(H * 0.33);

const chart1 = LightweightCharts.createChart(document.getElementById('chart1'),{{
  width:W, height:H1, layout:commonLayout, grid:commonGrid,
  timeScale:commonTS, localization:commonLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#333'}},
}});

const candle = chart1.addCandlestickSeries({{
  upColor:'#26A69A', downColor:'#FF5252', borderVisible:false,
  wickUpColor:'#26A69A', wickDownColor:'#FF5252',
}});
candle.setData(data.candles);

const e24 = chart1.addLineSeries({{color:'#FF6D00',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e24.setData(data.ema24);

const e52 = chart1.addLineSeries({{color:'#AA00FF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e52.setData(data.ema52);

const e104 = chart1.addLineSeries({{color:'#FFFFFF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e104.setData(data.ema104);

const chart2 = LightweightCharts.createChart(document.getElementById('chart2'),{{
  width:W, height:H2, layout:commonLayout, grid:commonGrid,
  timeScale:commonTS, localization:commonLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#333'}},
}});

const hist = chart2.addHistogramSeries({{
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
hist.setData(data.hist);

const macd = chart2.addLineSeries({{color:'#2962FF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
macd.setData(data.macd);

const sig = chart2.addLineSeries({{color:'#FF6D00',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
sig.setData(data.signal);

const pairs = [[chart1,candle],[chart2,hist]];
let syncing = false;

pairs.forEach(([sc])=>{{
  sc.subscribeCrosshairMove(p=>{{
    if(syncing) return; syncing=true;
    pairs.forEach(([tc,ts])=>{{
      if(tc===sc) return;
      if(p.time){{
        const pr = ts.coordinateToPrice(p.point?p.point.y:0);
        tc.setCrosshairPosition(pr??0, p.time, ts);
      }} else tc.clearCrosshairPosition();
    }});
    syncing=false;
  }});
  sc.timeScale().subscribeVisibleLogicalRangeChange(r=>{{
    if(syncing||!r) return; syncing=true;
    pairs.forEach(([tc])=>{{ if(tc!==sc) tc.timeScale().setVisibleLogicalRange(r); }});
    syncing=false;
  }});
}});

window.addEventListener('resize',()=>{{
  const nw=window.innerWidth;
  pairs.forEach(([c])=>c.applyOptions({{width:nw}}));
}});
</script>
</body>
</html>
"""

st.components.v1.html(html, height=int(700), scrolling=False)