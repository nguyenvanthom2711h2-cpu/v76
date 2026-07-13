import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings
import pytz
from scipy.signal import argrelextrema

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v163", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (Ổn định hơn v162)
# ==========================================
def get_live_price(symbol):
    try:
        # Tải 1 ngày gần nhất, interval 1 phút để lấy giá vừa khớp
        t = yf.Ticker(symbol)
        df_live = t.history(period='1d', interval='1m')
        if not df_live.empty:
            return df_live['Close'].iloc[-1]
        return None
    except:
        return None

# ==========================================
# 3. THUẬT TOÁN PHÂN KỲ & CHỈ BÁO
# ==========================================
def detect_divergence(df, order=5):
    try:
        if len(df) < 35: return "-"
        # Sử dụng High/Low để tìm đỉnh đáy chính xác hơn
        high_idx = argrelextrema(df['High'].values, np.greater, order=order)[0]
        low_idx = argrelextrema(df['Low'].values, np.less, order=order)[0]
        
        if len(low_idx) >= 2:
            i2, i1 = low_idx[-2], low_idx[-1]
            if df['Low'].iloc[i1] < df['Low'].iloc[i2] and df['rsi_val'].iloc[i1] > df['rsi_val'].iloc[i2]:
                if (len(df) - 1 - i1) < 12: return "HỘI TỤ (MUA) 🚀"
        if len(high_idx) >= 2:
            i2, i1 = high_idx[-2], high_idx[-1]
            if df['High'].iloc[i1] > df['High'].iloc[i2] and df['rsi_val'].iloc[i1] < df['rsi_val'].iloc[i2]:
                if (len(df) - 1 - i1) < 12: return "PHÂN KỲ (BÁN) 📉"
        return "-"
    except: return "-"

def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        col = 'Close'
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        delta = df[col].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        
        df['div_status'] = detect_divergence(df)
        return df
    except: return None

def fetch_data_v163(symbol, tf):
    try:
        # Tối ưu hóa interval để tránh bị Yahoo chặn
        if tf in ['15m', '30m']: f_tf, p = tf, '5d'
        elif tf in ['1h', '2h', '4h', '8h', '12h']: f_tf, p = '1h', '730d'
        else: f_tf, p = '1d', 'max'
            
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=15)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # Logic gộp nến
        rule_map = {'2h':'2h','4h':'4h','8h':'8h','12h':'12h','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)", "HỘI TỤ (MUA) 🚀"]: return 'color: #00ff88;'
    if val in ["GIẢM", "CHỈNH (-)", "PHÂN KỲ (BÁN) 📉"]: return 'color: #ff4444;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v163</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs([asset['name'] for asset in LIST_ASSETS])

    for i, asset in enumerate(LIST_ASSETS):
        with tabs[i]:
            status_placeholder = st.empty()
            table_placeholder = st.empty()
            
            with st.spinner(f"Đang quét {asset['name']}..."):
                # Lấy giá Live cho tài sản
                live_p = get_live_price(asset['symbol'])
                data_rows = []
                
                for tf in TIMEFRAMES:
                    if asset['symbol'] == "^VNINDEX" and any(x in tf for x in ['m', 'h']):
                        continue
                    
                    df_ind = fetch_data_v163(asset['symbol'], tf)
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        # Nếu lấy được giá live thì dùng, không thì dùng giá đóng nến cuối
                        p_val = live_p if live_p is not None else float(last['Close'])
                        
                        r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                        if r > r9 and r > r45: r_stat = "TĂNG"
                        elif r < r9 and r < r45: r_stat = "GIẢM"
                        elif r9 > r > r45: r_stat = "CHỈNH (-)"
                        else: r_stat = "HỒI (+)"
                        
                        data_rows.append({
                            "Khung": tf.upper(), 
                            "Xu hướng": "TĂNG" if p_val > last['ma20'] else "GIẢM", 
                            "RSI 9/45": r_stat,
                            "Phân kỳ RSI": last['div_status'],
                            "Giá/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", 
                            "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                            "RSI": int(r), 
                            "Giá": f"{p_val:,.1f}"
                        })

                if data_rows:
                    status_placeholder.success(f"💠 {asset['name']} | Live: {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
                    # Sử dụng st.table để ổn định hơn st.dataframe trong một số trường hợp
                    df_final = pd.DataFrame(data_rows)
                    try:
                        table_placeholder.table(df_final.style.map(style_text))
                    except:
                        table_placeholder.table(df_final.style.applymap(style_text))

    # Tự động refresh sau 2 phút (tăng thời gian để tránh bị Yahoo chặn IP)
    time.sleep(120)
    st.rerun()

if __name__ == "__main__":
    main()
