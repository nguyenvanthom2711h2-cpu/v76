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
# 1. CẤU HÌNH & GIẢ LẬP
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "bin_sym": "BTCUSDT"},
    {"name": "VÀNG", "symbol": "GC=F", "bin_sym": None}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "bin_sym": None}
]
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '1w', '1m']

st.set_page_config(page_title="Master Trade v177", layout="wide")

# Tạo Session giả lập trình duyệt để lách luật Yahoo
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (BYPASS YAHOO)
# ==========================================
def get_live_price_v177(asset):
    # Ưu tiên Binance cho Bitcoin để chắc chắn nhảy giá
    if asset['bin_sym']:
        try:
            res = session.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset['bin_sym']}", timeout=3)
            return float(res.json()['price']), "Binance API"
        except: pass
    
    # Với Vàng và Index, dùng Yahoo nhưng lấy nến 1 ngày gần nhất
    try:
        t = yf.Ticker(asset['symbol'], session=session)
        df = t.history(period='1d', interval='1m')
        if not df.empty:
            return float(df['Close'].iloc[-1]), "Yahoo Live"
    except: pass
    return None, "Blocked"

# ==========================================
# 3. THUẬT TOÁN CHỈ BÁO
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 40: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        c = 'Close'
        df['ma10'] = df[c].rolling(10).mean()
        df['ma20'] = df[c].rolling(20).mean()
        df['ma50'] = df[c].rolling(50).mean()
        
        delta = df[c].diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        ag = gain.ewm(alpha=1/14, adjust=False).mean()
        al = loss.ewm(alpha=1/14, adjust=False).mean()
        df['rsi_val'] = 100 - (100 / (1 + ag / al))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        
        hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
        li = argrelextrema(df['Low'].values, np.less, order=5)[0]
        df['div'] = "-"
        if len(li) >= 2 and df['Low'].iloc[li[-1]] < df['Low'].iloc[li[-2]] and df['rsi_val'].iloc[li[-1]] > df['rsi_val'].iloc[li[-2]]:
            if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2 and df['High'].iloc[hi[-1]] > df['High'].iloc[hi[-2]] and df['rsi_val'].iloc[hi[-1]] < df['rsi_val'].iloc[hi[-2]]:
            if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
        return df
    except: return None

def fetch_data_v177(asset, tf):
    try:
        # Nếu là Bitcoin, lấy nến từ Binance để bypass Yahoo
        if asset['bin_sym']:
            mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w', '1m':'1M'}
            bin_int = mapping.get(tf, '1h')
            url = f"https://api.binance.com/api/v3/klines?symbol={asset['bin_sym']}&interval={bin_int}&limit=200"
            res = session.get(url, timeout=5).json()
            df = pd.DataFrame(res, columns=['ts','Open','High','Low','Close','Vol','C_ts','Q_vol','Tr','T_b','T_q','Ig'])
            df[['Open','High','Low','Close']] = df[['Open','High','Low','Close']].astype(float)
            return calculate_indicators(df)
        
        # Với Vàng/Index, dùng Yahoo nhưng giảm thiểu yêu cầu
        ticker = yf.Ticker(asset['symbol'], session=session)
        p = '5d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
        f_tf = '1h' if ('h' in tf and tf != '1h') else ('1d' if tf == '3d' else tf)
        df = ticker.history(period=p, interval=f_tf)
        
        if df.empty: return None
        rule = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME'}
        if tf in rule:
            df = df.resample(rule[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v177</h2>", unsafe_allow_html=True)
    
    if st.sidebar.button("♻️ LÀM MỚI TOÀN BỘ"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph, table_ph = st.empty(), st.empty()
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                live_p, source = get_live_price_v177(asset)
                rows = []
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                    df = fetch_data_v177(asset, tf)
                    p_val = live_p if live_p else (df['Close'].iloc[-1] if df is not None else 0)
                    
                    if df is not None:
                        last = df.iloc[-1]
                        r = last['rsi_val']
                        rs = "TĂNG" if (r > last['rsi9'] and r > last['rsi45']) else "GIẢM"
                        rows.append({
                            "Khung": tf.upper(), "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), "Giá": f"{p_val:,.1f}"
                        })
                    else:
                        rows.append({"Khung": tf.upper(), "Xu hướng": "Yahoo Blocked", "RSI 9/45": "-", "Giá": f"{p_val:,.1f}" if p_val else "-"})

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {source} | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))

    time.sleep(300) # Tăng lên 5 phút để tránh bị Yahoo khóa IP lần nữa
    st.rerun()

if __name__ == "__main__":
    main()
