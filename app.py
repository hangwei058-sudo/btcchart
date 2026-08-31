import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import json

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.block-container{
    background:#000!important;
  }
  .block-container{padding:0.1rem 0.3rem 0!important;}
  [data-testid="stVerticalBlock"]{gap:0.04rem!important;}
  header,footer{display:none!important;}
  .stButton button{
    background:#111!important;color:#bbb!important;
    border:1px solid #2a2a2a!important;
    font-size:11px!important;height:24px!important;
    min-height:24px!important;padding:0 2px!important;
    border-radius:3px!important;transition:all .08s!important;
  }
  .stButton button:active{
    background:#1a6aff!important;color:#fff!important;
    transform:scale(.88)!important;
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

# 顶行：品种 + ◀ 当前周期 ▶
c1,c2,c3,c4,c5 = st.columns([1.2,1.2,0.5,1,0.5])
with c1:
    lbl = "● 黄金" if st.session_state.selected_symbol=="黄金 GOLD" else "黄金 GOLD"
    if st.button(lbl, key="g", use_container_width=True):
        st.session_state.selected_symbol = "黄金 GOLD"
with c2:
    lbl = "● BTC" if st.session_state.selected_symbol=="BTC/USDT" else "BTC/USDT"
    if st.button(lbl, key="b", use_container_width=True):
        st.session_state.selected_symbol = "BTC/USDT"
with c3:
    if st.button("◀", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx-1)%len(period_keys)]
with c4:
    st.markdown(
        f"<div style='text-align:center;color:#FFD700;font-weight:bold;"
        f"font-size:14px;line-height:24px'>{st.session_state.selected_label}</div>",
        unsafe_allow_html=True)
with c5:
    if st.button("▶", use_container_width=True):
        idx = period_keys.index(st.session_state.selected_label)
        st.session_state.selected_label = period_keys[(idx+1)%len(period_keys)]

# 时间级别按钮网格（9列，纯按钮不弹键盘）
n_cols = 9
for row_start in range(0, len(period_keys), n_cols):
    row_keys = period_keys[row_start:row_start+n_cols]
    cols = st.columns(n_cols)
    for i, key in enumerate(row_keys):
        is_active = (key == st.session_state.selected_label)
        label = f"●{key}" if is_active else key
        if cols[i].button(label, key=f"btn_{key}", use_container_width=True):
            st.session_state.selected_label = key

selected_label = st.session_state.selected_label
selected_symbol_label = st.session_state.selected_symbol
symbol = SYMBOL_CONFIG[selected_symbol_label]
rule = TIME_CONFIG[selected_label]
bar_seconds = BAR_SECONDS.get(selected_label, 3600)
is_btc = (symbol == "BTC/USDT")

BASE_FETCH_LIMIT = 50000

def get_base_interval(rule):
    r = rule.lower()
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
        bars = exchange.fetch_ohlcv('BTC/USDT', timeframe='1m', since=since, limit=per_call)
        if not bars: break
        all_bars += bars
        last_ts = bars[-1][0]
        if last_ts <= since: break
        since = last_ts + 60 * 1000
        if len(all_bars) >= total_limit: break
    return all_bars

@st.cache_data(ttl=120)
def get_btc_base_df():
    bars = fetch_btc_1m(BASE_FETCH_LIMIT)
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
def resample_data(symbol, rule):
    base_type = get_base_interval(rule)
    df = get_gold_df(base_type) if symbol=="GC=F" else get_btc_base_df()
    resampled = df.resample(rule).agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    ).dropna(subset=['open','high','low','close'])
    ema12 = resampled['close'].ewm(span=12,adjust=False).mean()
    ema26 = resampled['close'].ewm(span=26,adjust=False).mean()
    resampled['macd']   = ema12 - ema26
    resampled['macd_s'] = resampled['macd'].ewm(span=9,adjust=False).mean()
    resampled['macd_h'] = resampled['macd'] - resampled['macd_s']
    resampled['ema24']  = resampled['close'].ewm(span=24, adjust=False).mean()
    resampled['ema52']  = resampled['close'].ewm(span=52, adjust=False).mean()
    resampled['ema104'] = resampled['close'].ewm(span=104,adjust=False).mean()
    return resampled.tail(2000)

df = resample_data(symbol, rule)

candles,ema24_data,ema52_data,ema104_data=[],[],[],[]
macd_data,signal_data,hist_data=[],[],[]
prev_h = None

for idx,row in df.iterrows():
    t = int(idx.timestamp())
    candles.append({"time":t,"open":float(row['open']),"high":float(row['high']),
                    "low":float(row['low']),"close":float(row['close'])})
    if pd.notna(row['ema24']):  ema24_data.append({"time":t,"value":float(row['ema24'])})
    if pd.notna(row['ema52']):  ema52_data.append({"time":t,"value":float(row['ema52'])})
    if pd.notna(row['ema104']): ema104_data.append({"time":t,"value":float(row['ema104'])})
    if pd.notna(row['macd']):   macd_data.append({"time":t,"value":float(row['macd'])})
    if pd.notna(row['macd_s']): signal_data.append({"time":t,"value":float(row['macd_s'])})
    if pd.notna(row['macd_h']):
        v = float(row['macd_h'])
        if v >= 0:
            color="#26A69A" if (prev_h is None or pd.isna(prev_h) or v>=prev_h) else "#B2DFDB"
        else:
            color="#FF5252" if (prev_h is None or pd.isna(prev_h) or v<=prev_h) else "#FFCDD2"
        hist_data.append({"time":t,"value":v,"color":color})
        prev_h = v

last_price = candles[-1]['close'] if candles else 0
last_open  = candles[-1]['open']  if candles else 0
last_candle_time = candles[-1]['time'] if candles else 0

data_json = json.dumps({
    "candles":candles,"ema24":ema24_data,"ema52":ema52_data,
    "ema104":ema104_data,"macd":macd_data,"signal":signal_data,"hist":hist_data,
})

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  html,body{{margin:0;padding:0;background:#000;overflow:hidden;}}
  #chart1,#chart2{{width:100%;}}
  #wrap1{{position:relative;}}

  /* 浮动价格框（右上角，可拖动） */
  #floatBox{{
    position:absolute;top:8px;right:6px;
    background:rgba(10,10,10,0.88);
    border:1px solid #333;border-radius:6px;
    padding:5px 10px;z-index:999;
    font-family:monospace;text-align:right;
    cursor:move;user-select:none;
    min-width:100px;
  }}
  #priceVal{{font-size:17px;font-weight:bold;color:#26A69A;}}
  #priceDiff{{font-size:10px;color:#888;margin-top:1px;}}
  #timerRow{{
    font-size:11px;color:#FFD700;
    margin-top:3px;border-top:1px solid #222;
    padding-top:3px;
  }}
  #timerLabel{{font-size:9px;color:#555;}}
</style>
</head>
<body>
<div id="wrap1">
  <div id="chart1"></div>
  <!-- 浮动框：价格 + 收盘倒计时合一 -->
  <div id="floatBox">
    <div id="priceVal">{last_price:.2f}</div>
    <div id="priceDiff">-- (--.--%%)</div>
    <div id="timerRow">
      <div id="timerLabel">下根K线收盘</div>
      <div id="timerVal">--:--</div>
    </div>
  </div>
</div>
<div id="chart2"></div>

<script>
const data = {data_json};
const BAR_SEC   = {bar_seconds};
const LAST_TS   = {last_candle_time};
const IS_BTC    = {'true' if is_btc else 'false'};
const INIT_PRICE= {last_price};
const INIT_OPEN = {last_open};

// 拖动浮动框
(function(){{
  const el = document.getElementById('floatBox');
  let ox,oy,sx,sy,dragging=false;
  el.addEventListener('touchstart',e=>{{
    const t=e.touches[0];
    ox=el.offsetLeft; oy=el.offsetTop;
    sx=t.clientX; sy=t.clientY; dragging=true;
    e.preventDefault();
  }},{{passive:false}});
  document.addEventListener('touchmove',e=>{{
    if(!dragging)return;
    const t=e.touches[0];
    el.style.right='auto';
    el.style.left=(ox+t.clientX-sx)+'px';
    el.style.top =(oy+t.clientY-sy)+'px';
    e.preventDefault();
  }},{{passive:false}});
  document.addEventListener('touchend',()=>dragging=false);
  el.addEventListener('mousedown',e=>{{
    ox=el.offsetLeft; oy=el.offsetTop;
    sx=e.clientX; sy=e.clientY; dragging=true;
  }});
  document.addEventListener('mousemove',e=>{{
    if(!dragging)return;
    el.style.right='auto';
    el.style.left=(ox+e.clientX-sx)+'px';
    el.style.top =(oy+e.clientY-sy)+'px';
  }});
  document.addEventListener('mouseup',()=>dragging=false);
}})();

const BG='#000';
const commonLayout={{background:{{color:BG}},textColor:'#ccc'}};
const commonGrid  ={{vertLines:{{color:'#1a1a1a'}},horzLines:{{color:'#1a1a1a'}}}};
const commonTS    ={{timeVisible:true,secondsVisible:false,borderColor:'#2a2a2a'}};
const commonLoc   ={{timeFormatter:ts=>{{
  const d=new Date((ts+8*3600)*1000);
  const mo=String(d.getUTCMonth()+1).padStart(2,'0');
  const dd=String(d.getUTCDate()).padStart(2,'0');
  const hh=String(d.getUTCHours()).padStart(2,'0');
  const mn=String(d.getUTCMinutes()).padStart(2,'0');
  return mo+'/'+dd+' '+hh+':'+mn;
}}}};

const W=window.innerWidth, H=window.innerHeight;
const CTRL=60, avail=H-CTRL;
const H1=Math.floor(avail*0.63), H2=Math.floor(avail*0.35);

const chart1=LightweightCharts.createChart(document.getElementById('chart1'),{{
  width:W,height:H1,layout:commonLayout,grid:commonGrid,
  timeScale:commonTS,localization:commonLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});
const candle=chart1.addCandlestickSeries({{
  upColor:'#26A69A',downColor:'#FF5252',borderVisible:false,
  wickUpColor:'#26A69A',wickDownColor:'#FF5252',
  lastValueVisible:true,priceLineVisible:true,
}});
candle.setData(data.candles);

const e24=chart1.addLineSeries({{color:'#FF6D00',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e24.setData(data.ema24);
const e52=chart1.addLineSeries({{color:'#AA00FF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e52.setData(data.ema52);
const e104=chart1.addLineSeries({{color:'#FFFFFF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
e104.setData(data.ema104);

const chart2=LightweightCharts.createChart(document.getElementById('chart2'),{{
  width:W,height:H2,layout:commonLayout,grid:commonGrid,
  timeScale:commonTS,localization:commonLoc,
  crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  rightPriceScale:{{borderColor:'#2a2a2a'}},
}});
const hist=chart2.addHistogramSeries({{
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
hist.setData(data.hist);
const macd=chart2.addLineSeries({{color:'#2962FF',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
macd.setData(data.macd);
const sig=chart2.addLineSeries({{color:'#FF6D00',lineWidth:1,
  lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
sig.setData(data.signal);

// 更新浮动价格
function updatePriceBox(price,open){{
  const el=document.getElementById('priceVal');
  const diff=price-open;
  const pct=open>0?diff/open*100:0;
  el.textContent=price.toFixed(2);
  el.style.color=price>=open?'#26A69A':'#FF5252';
  const s=diff>=0?'+':'';
  document.getElementById('priceDiff').textContent=
    s+diff.toFixed(2)+' ('+s+pct.toFixed(2)+'%)';
}}
updatePriceBox(INIT_PRICE,INIT_OPEN);

// 收盘倒计时
function updateTimer(){{
  const now=Math.floor(Date.now()/1000);
  let rem=LAST_TS+BAR_SEC-now;
  let str;
  if(rem<=0){{str='⏰ 收盘';}}
  else if(rem>=3600){{
    const h=Math.floor(rem/3600);
    const m=Math.floor((rem%3600)/60);
    const s=rem%60;
    str=h+'h '+String(m).padStart(2,'0')+'m '+String(s).padStart(2,'0')+'s';
  }}else if(rem>=60){{
    const m=Math.floor(rem/60);
    const s=rem%60;
    str=m+'m '+String(s).padStart(2,'0')+'s';
  }}else{{str=rem+'s';}}
  document.getElementById('timerVal').textContent='⏱ '+str;
}}
updateTimer();
setInterval(updateTimer,1000);

// 实时价格（每5秒）
async function fetchLive(){{
  try{{
    if(IS_BTC){{
      const r=await fetch('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT');
      const j=await r.json();
      const p=parseFloat(j.data[0].last);
      const o=parseFloat(j.data[0].open24h);
      if(!isNaN(p)){{
        const lb=data.candles[data.candles.length-1];
        candle.update({{...lb,close:p,high:Math.max(lb.high,p),low:Math.min(lb.low,p)}});
        updatePriceBox(p,o);
      }}
    }}else{{
      const r=await fetch('https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=1m&range=1d');
      const j=await r.json();
      const p=j.chart.result[0].meta.regularMarketPrice;
      const o=j.chart.result[0].meta.chartPreviousClose;
      if(p&&!isNaN(p)){{
        const lb=data.candles[data.candles.length-1];
        candle.update({{...lb,close:p,high:Math.max(lb.high,p),low:Math.min(lb.low,p)}});
        updatePriceBox(p,o||lb.open);
      }}
    }}
  }}catch(e){{}}
}}
fetchLive();
setInterval(fetchLive,5000);

// 同步十字线+时间轴
const pairs=[[chart1,candle],[chart2,hist]];
let syncing=false;
pairs.forEach(([sc])=>{{
  sc.subscribeCrosshairMove(p=>{{
    if(syncing)return;syncing=true;
    pairs.forEach(([tc,ts])=>{{
      if(tc===sc)return;
      if(p.time){{const pr=ts.coordinateToPrice(p.point?p.point.y:0);
        tc.setCrosshairPosition(pr??0,p.time,ts);
      }}else tc.clearCrosshairPosition();
    }});syncing=false;
  }});
  sc.timeScale().subscribeVisibleLogicalRangeChange(r=>{{
    if(syncing||!r)return;syncing=true;
    pairs.forEach(([tc])=>{{if(tc!==sc)tc.timeScale().setVisibleLogicalRange(r);}});
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

st.components.v1.html(html, height=700, scrolling=False)