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
    {"name": "BITCOIN", "symbol": "BTC-USD", "binance": "BTCUSDT"},
    {"name": "VÀNG", "symbol": "GC=F", "binance": None}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "binance": None}
]
# Các khung thời gian hỗ trợ
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '1w', '1m']

st.set_page_config(page_title="Master Trade v174", layout="wide")

# ==========================================
# 2. HÀM LẤY DỮ LIỆU TỪ BINANCE (CHO BITCOIN)
# ==========================================
def fetch_binance_data(symbol, interval):
    """Lấy dữ liệu nến trực tiếp từ Binance API (Bypass Yahoo hoàn toàn)"""
    try:
        # Mapping timeframe sang Binance interval
        mapping = {'15m':'15m', '30m':'30m', '1h':'1h', '2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '1d':'1d', '1w':'1w', '1m':'1M'}
        bin_int = mapping.get(interval, '1h')
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={bin_int}&limit=200"
        res = requests.get(url, timeout=5).json()
        
        df = pd.DataFrame(res, columns=['ts', 'Open', 'High', 'Low', 'Close', 'Vol', 'Close_ts', 'Quote_vol', 'Trades', 'Taker_buy_base', 'Taker_buy_quote', 'Ignore'])
        df['Close'] = df['Close'].astype(float)
        df['High'] = df['High'].astype(float)
        df['Low'] = df['Low'].astype(float)
        df['Open'] = df['Open'].astype(float)
        return df
    except:
        return None

def get_live_price_binance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        return float(requests.get(url, timeout=3).json()['price'])
    except:
        return None

# ==========================================
# 3. THUẬT TOÁN CHỈ BÁO
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 45: return None
    try:
        df = df.copy()
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
        
        # Divergence
        hi = argrelextrema(df['High'].values, np.greater, order=5)[0]
        li = argrelextrema(df['Low'].values, np.less, order=5)[0]
        df['div'] = "-"
        if len(li) >= 2 and df['Low'].iloc[li[-1]] < df['Low'].iloc[li[-2]] and df['rsi_val'].iloc[li[-1]] > df['rsi_val'].iloc[li[-2]]:
            if (len(df)-1-li[-1]) < 10: df.loc[df.index[-1], 'div'] = "HỘI TỤ (MUA) 🚀"
        if len(hi) >= 2 and df['High'].iloc[hi[-1]] > df['High'].iloc[hi[-2]] and df['rsi_val'].iloc[hi[-1]] < df['rsi_val'].iloc[hi[-2]]:
            if (len(df)-1-hi[-1]) < 10: df.loc[df.index[-1], 'div'] = "PHÂN KỲ (BÁN) 📉"
        return df
    except: return None

# ==========================================
# 4. QUY TRÌNH QUÉT CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v174</h2>", unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.header("Cài đặt")
    if st.sidebar.button("♻️ RESET & CLEAR CACHE"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_ph = st.empty()
            table_ph = st.empty()
            
            with st.spinner(f"Đang đồng bộ {asset['name']}..."):
                rows = []
                # --- XỬ LÝ RIÊNG CHO BITCOIN (BINANCE) ---
                if asset['binance']:
                    live_p = get_live_price_binance(asset['binance'])
                    for tf in TIMEFRAMES:
                        df_bin = fetch_binance_data(asset['binance'], tf)
                        df_ind = calculate_indicators(df_bin)
                        if df_ind is not None:
                            last = df_ind.iloc[-1]
                            p_val = live_p if live_p else last['Close']
                            r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                            rs = "TĂNG" if (r > r9 and r > r45) else ("GIẢM" if (r < r9 and r < r45) else "CHỈNH")
                            
                            rows.append({
                                "Khung": tf.upper(), "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                                "RSI 9/45": rs, "Phân kỳ RSI": last['div'],
                                "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                                "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                                "RSI": int(r), "Giá": f"{p_val:,.1f}"
                            })
                    source_str = "Sàn Binance (Live)"
                
                # --- XỬ LÝ CHO VÀNG & VNINDEX (YAHOO) ---
                else:
                    ticker = yf.Ticker(asset['symbol'])
                    live_p = ticker.fast_info['last_price']
                    for tf in TIMEFRAMES:
                        if asset['symbol'] == "^VNINDEX" and ('m' in tf or 'h' in tf): continue
                        p_yf = '5d' if 'm' in tf else 'max'
                        # Lấy dữ liệu nến
                        df_yf = ticker.history(period=p_yf, interval=tf)
                        df_ind = calculate_indicators(df_yf)
                        if df_ind is not None:
                            last = df_ind.iloc[-1]
                            p_val = live_p if live_p else last['Close']
                            rows.append({
                                "Khung": tf.upper(), "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                                "RSI 9/45": "TĂNG" if last['rsi_val'] > last['rsi9'] else "GIẢM",
                                "Phân kỳ RSI": last['div'], "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                                "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                                "RSI": int(last['rsi_val']), "Giá": f"{p_val:,.1f}"
                            })
                    source_str = "Yahoo Finance"

                if rows:
                    status_ph.success(f"💠 {asset['name']} | Nguồn: {source_str} | {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    table_ph.table(pd.DataFrame(rows).style.map(style_text))
                else:
                    status_ph.error("⚠️ Không thể kết nối dữ liệu. Vui lòng thử lại.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
