import streamlit as st
import ccxt
import pandas as pd
import json

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],.block-container {
    background:#000 !important; padding:0 !important; margin:0 !important;
  }
  header,footer,[data-testid="stToolbar"] { display:none !important; }
</style>
""", unsafe_allow_html=True)

SYMBOL_MAP   = {'GOLD': 'XAU/USDT:USDT', 'BTC': 'BTC/USDT:USDT'}
BYBIT_TICKER = {'GOLD': 'XAUUSDT',        'BTC': 'BTCUSDT'}
SYMBOL_LABEL = {'GOLD': '黄金 GOLD',      'BTC': 'BTC/USDT'}

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

params = st.query_params
sel_sym    = params.get('symbol', 'GOLD')
sel_period = params.get('period', '1h')
if sel_sym    not in SYMBOL_MAP:  sel_sym    = 'GOLD'
if sel_period not in TIME_CONFIG: sel_period = '1h'

ccxt_symbol  = SYMBOL_MAP[sel_sym]
bybit_ticker = BYBIT_TICKER[sel_sym]
rule         = TIME_CONFIG[sel_period]
bar_seconds  = BAR_SECONDS.get(sel_period, 3600)

def fetch_config(period):
    r = TIME_CONFIG[period].lower()
    if r.endswith('d'):
        d = int(r[:-1])
        return '1d', TIME_CONFIG[period], min(2000, d*500+100)
    elif r.endswith('h'):
        h = int(r[:-1])
        return '1h', TIME_CONFIG[period], min(5000, h*500+200)
    else:
        m = int(r[:-3])
        return '1m', TIME_CONFIG[period], min(20000, m*500+200)

@st.cache_data(ttl=60)
def fetch_bybit(symbol, base_tf, total):
    try:
        ex = ccxt.bybit({'options':{'defaultType':'linear'}})
        ms = {'1m':60000,'1h':3600000,'1d':86400000}[base_tf]
        since = ex.milliseconds() - total * ms
        bars = []
        while len(bars) < total:
            batch = ex.fetch_ohlcv(symbol, timeframe=base_tf, since=since, limit=1000)
            if not batch: break
            bars += batch
            last = batch[-1][0]
            if last <= since: break
            since = last + ms
            if len(batch) < 1000: break
        return bars
    except:
        return []

@st.cache_data(ttl=60)
def get_data(symbol, period):
    base_tf, resample_rule, total = fetch_config(period)
    bars = fetch_bybit(symbol, base_tf, total)
    if not bars: return pd.DataFrame()

    df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[~df.index.duplicated(keep='last')].sort_index()

    r = resample_rule.lower()
    if (r=='1h' and base_tf=='1h') or (r=='1d' and base_tf=='1d') or (r=='1min' and base_tf=='1m'):
        rs = df.copy()
    else:
        rs = df.resample(resample_rule).agg(
            {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
        ).dropna(subset=['open','high','low','close'])

    rs = rs.copy()
    e12 = rs['close'].ewm(span=12,adjust=False).mean()
    e26 = rs['close'].ewm(span=26,adjust=False).mean()
    rs['macd']   = e12 - e26
    rs['macd_s'] = rs['macd'].ewm(span=9,  adjust=False).mean()
    rs['macd_h'] = rs['macd'] - rs['macd_s']
    rs['ema24']  = rs['close'].ewm(span=24, adjust=False).mean()
    rs['ema52']  = rs['close'].ewm(span=52, adjust=False).mean()
    rs['ema104'] = rs['close'].ewm(span=104,adjust=False).mean()
    return rs.tail(2000)

df = get_data(ccxt_symbol, sel_period)

candles,ema24_d,ema52_d,ema104_d,macd_d,sig_d,hist_d = [],[],[],[],[],[],[]
prev_h = None

for idx, row in df.iterrows():
    t = int(idx.timestamp())
    candles.append({"time":t,"open":float(row['open']),"high":float(row['high']),
                    "low":float(row['low']),"close":float(row['close'])})
    for col,arr in [('ema24',ema24_d),('ema52',ema52_d),('ema104',ema104_d),
                     ('macd',macd_d),('macd_s',sig_d)]:
        if col in row.index and pd.notna(row[col]):
            arr.append({"time":t,"value":float(row[col])})
    if 'macd_h' in row.index and pd.notna(row['macd_h']):
        v = float(row['macd_h'])
        color = ("#26A69A" if (prev_h is None or pd.isna(prev_h) or v>=prev_h) else "#B2DFDB") if v>=0 else \
                ("#FF5252" if (prev_h is None or pd.isna(prev_h) or v<=prev_h) else "#FFCDD2")
        hist_d.append({"time":t,"value":v,"color":color})
        prev_h = v

last_price      = candles[-1]['close'] if candles else 0
last_open       = candles[-1]['open']  if candles else 0
last_candle_t   = candles[-1]['time']  if candles else 0

data_json = json.dumps({"candles":candles,"ema24":ema24_d,"ema52":ema52_d,
    "ema104":ema104_d,"macd":macd_d,"signal":sig_d,"hist":hist_d})

opts_html = "".join(f'<option value="{k}" {"selected" if k==sel_period else ""}>{k}</option>\n'
                    for k in period_keys)
prev_p = period_keys[(period_keys.index(sel_period)-1) % len(period_keys)]
next_p = period_keys[(period_keys.index(sel_period)+1) % len(period_keys)]

html = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#000;color:#ccc;font-family:-apple-system,sans-serif;overflow:hidden}}
#topbar{{display:flex;align-items:center;gap:3px;padding:3px 4px;height:34px;background:#000}}
.sb{{background:#111;color:#666;border:1px solid #1e1e1e;border-radius:3px;
     padding:3px 8px;font-size:11px;cursor:pointer;flex:1}}
.sb.on{{background:#0a1e38;color:#4da6ff;border-color:#1e4a8a}}
.sb:active{{background:#1a3a6a;color:#fff}}
#ps{{background:#111;color:#ddd;border:1px solid #1e1e1e;border-radius:3px;
     padding:2px 2px;font-size:12px;flex:1.4;height:27px}}
.nb{{background:#111;color:#777;border:1px solid #1e1e1e;border-radius:3px;
     width:27px;height:27px;font-size:13px;cursor:pointer;flex-shrink:0;
     display:flex;align-items:center;justify-content:center}}
.nb:active{{background:#1a3a6a;color:#fff;transform:scale(0.9)}}
#info{{color:#2a2a2a;font-size:9px;padding:0 4px 1px}}
#w1{{position:relative}}
#c1,#c2{{width:100%}}
#fb{{position:absolute;top:5px;right:62px;background:rgba(3,3,3,0.88);
     border:1px solid #1a1a1a;border-radius:5px;padding:3px 8px;
     z-index:999;text-align:right;pointer-events:none;min-width:82px}}
#fp{{font-size:14px;font-weight:bold;font-family:monospace}}
#fc{{font-size:9px;color:#444;margin-top:1px}}
#fcd{{font-size:10px;color:#b8860b;margin-top:2px;font-family:monospace}}
</style>
</head>
<body>
<div id="topbar">
  <button class="sb {'on' if sel_sym=='GOLD' else ''}" onclick="go('GOLD','{sel_period}')">黄金</button>
  <button class="sb {'on' if sel_sym=='BTC'  else ''}" onclick="go('BTC', '{sel_period}')">BTC</button>
  <select id="ps" onchange="go('{sel_sym}',this.value)">{opts_html}</select>
  <button class="nb" onclick="go('{sel_sym}','{prev_p}')">◀</button>
  <button class="nb" onclick="go('{sel_sym}','{next_p}')">▶</button>
</div>
<div id="info">{SYMBOL_LABEL[sel_sym]} · {sel_period} · {len(df)}条 · Bybit实时</div>
<div id="w1">
  <div id="c1"></div>
  <div id="fb">
    <div id="fp">{last_price:.2f}</div>
    <div id="fc">···</div>
    <div id="fcd">--:--</div>
  </div>
</div>
<div id="c2"></div>

<script>
function go(s,p){{
  try{{window.top.location.href='?symbol='+s+'&period='+p}}
  catch(e){{window.location.href='?symbol='+s+'&period='+p}}
}}

const D={data_json};
const BAR={bar_seconds}, LT={last_candle_t}, TK='{bybit_ticker}';

const lay={{background:{{color:'#000'}},textColor:'#bbb'}};
const grd={{vertLines:{{color:'#0e0e0e'}},horzLines:{{color:'#0e0e0e'}}}};
const tsc={{timeVisible:true,secondsVisible:false,borderColor:'#141414'}};
const loc={{timeFormatter:t=>{{
  const d=new Date((t+28800)*1000);
  return String(d.getUTCMonth()+1).padStart(2,'0')+'/'+
         String(d.getUTCDate()).padStart(2,'0')+' '+
         String(d.getUTCHours()).padStart(2,'0')+':'+
         String(d.getUTCMinutes()).padStart(2,'0');
}}}};

const W=window.innerWidth, H=window.innerHeight;
const av=H-46, H1=Math.floor(av*0.63), H2=Math.floor(av*0.35);

const ch1=LightweightCharts.createChart(document.getElementById('c1'),
  {{width:W,height:H1,layout:lay,grid:grd,timeScale:tsc,localization:loc,
    crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
    rightPriceScale:{{borderColor:'#141414'}}}});

const cnd=ch1.addCandlestickSeries({{upColor:'#26A69A',downColor:'#FF5252',
  borderVisible:false,wickUpColor:'#26A69A',wickDownColor:'#FF5252'}});
cnd.setData(D.candles);

[[D.ema24,'#FF6D00'],[D.ema52,'#9B30FF'],[D.ema104,'#FFFFFF']].forEach(([d,c])=>{{
  const s=ch1.addLineSeries({{color:c,lineWidth:1,lastValueVisible:false,
    priceLineVisible:false,crosshairMarkerVisible:false}});
  s.setData(d);
}});

const ch2=LightweightCharts.createChart(document.getElementById('c2'),
  {{width:W,height:H2,layout:lay,grid:grd,timeScale:tsc,localization:loc,
    crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
    rightPriceScale:{{borderColor:'#141414'}}}});

const hs=ch2.addHistogramSeries({{lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false}});
hs.setData(D.hist);
[[D.macd,'#2962FF'],[D.signal,'#FF6D00']].forEach(([d,c])=>{{
  const s=ch2.addLineSeries({{color:c,lineWidth:1,lastValueVisible:false,
    priceLineVisible:false,crosshairMarkerVisible:false}});
  s.setData(d);
}});

// 实时价格
let lo={last_open};
async function live(){{
  try{{
    const r=await fetch('https://api.bybit.com/v5/market/tickers?category=linear&symbol='+TK);
    const j=await r.json(); const t=j.result.list[0];
    const p=parseFloat(t.lastPrice), p24=parseFloat(t.prevPrice24h);
    document.getElementById('fp').textContent=p.toFixed(2);
    document.getElementById('fp').style.color=p>=lo?'#26A69A':'#FF5252';
    const pct=((p-p24)/p24*100).toFixed(2);
    const el=document.getElementById('fc');
    el.textContent=(pct>=0?'+':'')+pct+'%';
    el.style.color=pct>=0?'#26A69A':'#FF5252';
    const last=D.candles[D.candles.length-1];
    if(last) cnd.update({{time:last.time,open:last.open,
      high:Math.max(last.high,p),low:Math.min(last.low,p),close:p}});
  }}catch(e){{}}
}}
live(); setInterval(live,2000);

// 倒计时
function tick(){{
  let rem=(LT+BAR)-Math.floor(Date.now()/1000);
  if(rem<0)rem=0;
  const s=!rem?'⏰ 收盘':
    rem>=3600?Math.floor(rem/3600)+'h'+String(Math.floor(rem%3600/60)).padStart(2,'0')+'m'+String(rem%60).padStart(2,'0')+'s':
    rem>=60?Math.floor(rem/60)+'m'+String(rem%60).padStart(2,'0')+'s':rem+'s';
  document.getElementById('fcd').textContent=s;
  document.getElementById('fcd').style.color=rem<60?'#ff4444':rem<300?'#FF8C00':'#b8860b';
}}
tick(); setInterval(tick,1000);

// 同步十字线+时间轴
const pairs=[[ch1,cnd],[ch2,hs]]; let sy=false;
pairs.forEach(([sc])=>{{
  sc.subscribeCrosshairMove(p=>{{
    if(sy)return;sy=true;
    pairs.forEach(([tc,ts])=>{{
      if(tc===sc)return;
      p.time?tc.setCrosshairPosition(ts.coordinateToPrice(p.point?p.point.y:0)??0,p.time,ts)
            :tc.clearCrosshairPosition();
    }});sy=false;
  }});
  sc.timeScale().subscribeVisibleLogicalRangeChange(r=>{{
    if(sy||!r)return;sy=true;
    pairs.forEach(([tc])=>{{if(tc!==sc)tc.timeScale().setVisibleLogicalRange(r);}});
    sy=false;
  }});
}});
window.addEventListener('resize',()=>{{
  const nw=window.innerWidth;
  pairs.forEach(([c])=>c.applyOptions({{width:nw}}));
}});
</script>
</body>
</html>"""

st.components.v1.html(html, height=700, scrolling=False)