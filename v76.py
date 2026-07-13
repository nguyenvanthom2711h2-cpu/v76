import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings
import pytz
import requests
from scipy.signal import argrelextrema

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "bin_sym": "BTCUSDT"},
    {"name": "VÀNG", "symbol": "GC=F", "bin_sym": None}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "bin_sym": None}
]
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '1w']

st.set_page_config(page_title="Master Trade v178", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE THỰC TẾ (CHỐNG ĐỨNG GIÁ)
# ==========================================
def get_btc_price_ultra():
    """Lấy giá BTC từ Coinbase API - Cực kỳ ổn định trên Cloud"""
    try:
        res = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=3)
        return float(res.json()['data']['amount'])
    except:
        try:
            res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=3)
            return float(res.json()['price'])
        except: return None

def get_live_price_v178(asset):
    if "BTC" in asset['name']:
        p = get_btc_price_ultra()
        return p, "Coinbase/Binance"
    
    try:
        # Với Vàng và Index, thử dùng yfinance nhưng không dùng cache
        t = yf.Ticker(asset['symbol'])
        df = t.history(period='1d', interval='1m')
        if not df.empty: return df['Close'].iloc[-1], "Yahoo Live"
        return t.fast_info['last_price'], "Yahoo Fast"
    except:
        return None, "Blocked"

# ==========================================
# 3. HÀM LẤY DỮ LIỆU NẾN (BYPASS YAHOO)
# ==========================================
def fetch_candles_v178(asset, tf):
    try:
        # Nếu là Bitcoin, lấy nến từ Binance API (Không dùng Yahoo)
        if "BTC" in asset['name']:
            mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w'}
            itv = mapping.get(tf, '1h')
            url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={itv}&limit=100"
            res = requests.get(url, timeout=5).json()
            df = pd.DataFrame(res, columns=['ts','Open','High','Low','Close','Vol','C_ts','Q_vol','Tr','T_b','T_q','Ig'])
            df[['Open','High','Low','Close']] = df[['Open','High','Low','Close']].astype(float)
            return df
        
        # Với Vàng/Index, dùng yfinance tải nến
        ticker = yf.Ticker(asset['symbol'])
        p = '5d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
        f_tf = '1h' if ('h' in tf and tf != '1h') else ('1d' if tf == '3d' else tf)
        df = ticker.history(period=p, interval=f_tf)
        if df.empty: return None
        
        # Gộp nến nếu cần
        rule = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON'}
        if tf in rule:
            df = df.resample(rule[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        return df
    except: return None

# ==========================================
# 4. CHỈ BÁO & GIAO DIỆN
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 30: return None
    df = df.copy()
    c = 'Close'
    df['ma10'] = df[c].rolling(10).mean()
    df['ma20'] = df[c].rolling(20).mean()
    df['ma50'] = df[c].rolling(50).mean()
    delta = df[c].diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False).mean()
    al = loss.ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + ag / al))
    df['rsi9'] = df['rsi'].rolling(9).mean()
    df['rsi45'] = df['rsi'].rolling(45).mean()
    
    # Divergence
    df['div'] = "-"
    hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
    li = argrelextrema(df['Low'].values, np.less, order=5)[0]
    if len(li) >= 2 and df[c].iloc[li[-1]] < df[c].iloc[li[-2]] and df['rsi'].iloc[li[-1]] > df['rsi'].iloc[li[-2]]:
        df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
    if len(hi) >= 2 and df[c].iloc[hi[-1]] > df[c].iloc[hi[-2]] and df['rsi'].iloc[hi[-1]] < df['rsi'].iloc[hi[-2]]:
        df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
    return df

def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v178</h2>", unsafe_allow_html=True)
    
    # Nút ép reset
    if st.sidebar.button("♻️ RESET DỮ LIỆU CŨ"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph, table_ph = st.empty(), st.empty()
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                # 1. LẤY GIÁ LIVE (ĐẢM BẢO NHẢY SỐ)
                live_p, src = get_live_price_v178(asset)
                
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    
                    # 2. LẤY NẾN & TÍNH CHỈ BÁO
                    df_raw = fetch_candles_v178(asset, tf)
                    df = calculate_indicators(df_raw)
                    
                    if df is not None:
                        last = df.iloc[-1]
                        p_val = live_p if live_p else last['Close']
                        r = last['rsi']
                        rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                        
                        rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, 
                            "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), 
                            "Giá": f"{p_val:,.1f}"
                        })
                    else:
                        rows.append({"Khung": tf.upper(), "Xu hướng": "Yahoo Blocked", "Giá": f"{live_p:,.1f}" if live_p else "-"})

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {src} | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
