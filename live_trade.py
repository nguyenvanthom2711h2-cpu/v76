import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import time
import warnings
import pytz
import requests
import random
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

st.set_page_config(page_title="Master Trade v181", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (KHÔNG DÙNG YAHOO CHO BTC)
# ==========================================
def get_price_forced_v181(asset_name, symbol, bin_sym):
    """Hàm lấy giá mới nhất, bỏ qua hoàn toàn Yahoo nếu là Bitcoin"""
    if "BITCOIN" in asset_name:
        # Thử Binance trước
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT&cb={random.random()}"
            res = requests.get(url, timeout=3)
            return float(res.json()['price']), "Binance Live"
        except:
            # Dự phòng CoinGecko
            try:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&cb={random.random()}"
                res = requests.get(url, timeout=3)
                return float(res.json()['bitcoin']['usd']), "CoinGecko Live"
            except:
                return None, "API Error"
    else:
        # Vàng và Index dùng Yahoo
        try:
            t = yf.Ticker(symbol)
            df = t.history(period='1d', interval='1m')
            if not df.empty: return df['Close'].iloc[-1], "Yahoo Live"
            return t.fast_info['last_price'], "Yahoo Fast"
        except:
            return None, "Yahoo Blocked"

# ==========================================
# 3. LẤY DỮ LIỆU NẾN
# ==========================================
def fetch_candles_forced_v181(asset_name, bin_sym, symbol, tf):
    try:
        if "BITCOIN" in asset_name:
            mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w'}
            itv = mapping.get(tf, '1h')
            url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={itv}&limit=150&cb={random.random()}"
            res = requests.get(url, timeout=5).json()
            df = pd.DataFrame(res, columns=['ts','Open','High','Low','Close','Vol','C_ts','Q_vol','Tr','T_b','T_q','Ig'])
            df[['Open','High','Low','Close']] = df[['Open','High','Low','Close']].astype(float)
        else:
            t = yf.Ticker(symbol)
            df = t.history(period='max' if 'd' in tf else '5d', interval=tf)
            if df.empty: return None
        
        # Chỉ báo
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
        df['rsi9'], df['rsi45'] = df['rsi'].rolling(9).mean(), df['rsi'].rolling(45).mean()
        
        # Phân kỳ
        df['div'] = "-"
        hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
        li = argrelextrema(df['Low'].values, np.less, order=5)[0]
        if len(li) >= 2 and df[c].iloc[li[-1]] < df[c].iloc[li[-2]] and df['rsi'].iloc[li[-1]] > df['rsi'].iloc[li[-2]]:
            if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2 and df[c].iloc[hi[-1]] > df[c].iloc[hi[-2]] and df['rsi'].iloc[hi[-1]] < df['rsi'].iloc[hi[-2]]:
            if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
        return df
    except: return None

def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v181</h2>", unsafe_allow_html=True)
    
    if st.sidebar.button("♻️ RESET CACHE (NHẤN KHI GIÁ ĐỨNG)"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph, table_ph = st.empty(), st.empty()
            
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                # 1. LẤY GIÁ LIVE THỰC TẾ
                p_live, src = get_price_forced_v181(asset['name'], asset['symbol'], asset['bin_sym'])
                
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    
                    df = fetch_candles_forced_v181(asset['name'], asset['bin_sym'], asset['symbol'], tf)
                    if df is not None:
                        last = df.iloc[-1]
                        p_val = p_live if p_live else last['Close']
                        r = last['rsi']
                        rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                        
                        rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), "Giá": f"{p_val:,.1f}"
                        })

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {src} | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))
                else:
                    st.error("⚠️ Không thể kết nối dữ liệu nến.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
