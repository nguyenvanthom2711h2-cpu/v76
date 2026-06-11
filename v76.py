import streamlit as st
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz
import requests
import os, sys, contextlib

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {}

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, 
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Đầy đủ 12 khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Master Dashboard v144", layout="wide")

@contextlib.contextmanager
def mute_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try: yield
        finally: sys.stdout = old_stdout

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RMA & PIVOT SR)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['ma10'] = df['Close'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['Close'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(50, min_periods=1).mean()
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

def get_sr_levels(df, curr_p):
    try:
        h, l = df['High'].values, df['Low'].values
        win = 3
        p_h = [h[i] for i in range(win, len(df)-win) if all(h[i]>=h[i-j] for j in range(1,win+1)) and all(h[i]>=h[i+j] for j in range(1,win+1))]
        p_l = [l[i] for i in range(win, len(df)-win) if all(l[i]<=l[i-j] for j in range(1,win+1)) and all(l[i]<=l[i+j] for j in range(1,win+1))]
        sup = max([x for x in p_h+p_l if x < curr_p * 0.999]) if [x for x in p_h+p_l if x < curr_p * 0.999] else min(l)
        res = min([x for x in p_h+p_l if x > curr_p * 1.001]) if [x for x in p_h+p_l if x > curr_p * 1.001] else max(h)
        return sup, res
    except: return 0, 0

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU TẬP TRUNG
# ==========================================
@st.cache_data(ttl=60)
def fetch_asset_bundle(symbol):
    try:
        with mute_stdout():
            dh = yf.download(symbol, period='730d', interval='1h', progress=False)
            dd = yf.download(symbol, period='max', interval='1d', progress=False)
            dm = yf.download(symbol, period='7d', interval='15m', progress=False)
        for d in [dh, dd, dm]:
            if not d.empty and isinstance(d.columns, pd.MultiIndex): 
                d.columns = d.columns.get_level_values(0)
        return {"1h": dh, "1d": dd, "15m": dm}
    except: return None

def get_resampled_tf(bundle, tf):
    try:
        if 'm' in tf and tf != '1m' and tf != '3m': src = bundle['15m']
        elif any(x in tf for x in ['h', 'H']): src = bundle['1h']
        else: src = bundle['1d']
        if src is None or src.empty: return None
        rule_map = {'15m':'15min','30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = src.resample(rule_map[tf]).agg(logic).dropna()
        else: df = src
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val): # ĐÃ THỐNG NHẤT TÊN HÀM
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    if val == "YẾU": return 'color: #f1c40f; font-weight: bold'
    return ''

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v144</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        bundle = fetch_asset_bundle(asset['symbol'])
        if bundle and not bundle['1d'].empty:
            price_src = bundle['15m'] if not bundle['15m'].empty else bundle['1h']
            live_p = float(price_src['Close'].iloc[-1])
            
            with st.expander(f"💠 {asset['name']} | Giá HT: {live_p:,.1f}", expanded=True):
                data_rows, sync_list = [], []
                for tf in TIMEFRAMES:
                    if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                    
                    df_ind = get_resampled_tf(bundle, tf)
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        p_v = float(last['Close'])
                        r, r9, r45 = float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                        sup, res = get_sr_levels(df_ind, p_v)
                        
                        if r > r9 and r > r45: r_s, r_c = "TĂNG", 1
                        elif r < r9 and r < r45: r_s, r_c = "GIẢM", -1
                        elif r > r45 and r < r9: r_s, r_c = "CHỈNH (-)", 0
                        else: r_s, r_c = "HỒI (+)", 0
                        
                        agreement = "-"
                        if sync_list:
                            prev = sync_list[-1]
                            key = f"{asset['name']}_{prev['tf']}_{tf}"
                            if r_c == 1 and prev['code'] == 1:
                                agreement = "MUA (↑)"
                                if st.session_state.last_alerts.get(key) != "BUY":
                                    st.session_state.last_alerts[key] = "BUY"
                            elif r_c == -1 and prev['code'] == -1:
                                agreement = "BÁN (↓)"
                                if st.session_state.last_alerts.get(key) != "SELL":
                                    st.session_state.last_alerts[key] = "SELL"
                        
                        sync_list.append({"tf": tf, "code": r_c})
                        def sign(v1, v2): return "TĂNG" if v1 > v2 else "GIẢM"
                        
                        data_rows.append({
                            "Khung": tf.upper(), "Sóng": sign(p_v, last['ma20']),
                            "Đồng thuận": agreement, "RSI 9/45": r_s,
                            "P/MA50": sign(p_v, last['ma50']), "MA 10/20": sign(last['ma10'], last['ma20']),
                            "Hỗ trợ": f"{sup:,.1f}", "Kháng cự": f"{res:,.1f}",
                            "RSI": int(r), "Giá": f"{p_v:,.1f}"
                        })
                
                if data_rows:
                    df_final = pd.DataFrame(data_rows)
                    # SỬ DỤNG .style.map VÀ style_text ĐÃ FIX TÊN
                    st.table(df_final.style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
        else:
            st.warning(f"🔄 Đang kết nối lại nguồn dữ liệu cho {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
