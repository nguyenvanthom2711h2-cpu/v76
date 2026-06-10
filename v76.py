import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz
import requests

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F"}, # Dùng Futures để ổn định nhất trên Web
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v109", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        delta = df['Close'].diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. BỘ MÁY TẢI DỮ LIỆU "VƯỢT RÀO"
# ==========================================
@st.cache_data(ttl=60)
def get_master_data(symbol):
    """Tải dữ liệu mồi với Header giả lập trình duyệt để tránh chặn IP"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    try:
        # Tải nến 1H (730 ngày)
        d1h = yf.download(symbol, period='730d', interval='1h', progress=False, session=session, timeout=15)
        if isinstance(d1h.columns, pd.MultiIndex): d1h.columns = d1h.columns.get_level_values(0)
        
        # Tải nến 1D (Max lịch sử)
        d1d = yf.download(symbol, period='max', interval='1d', progress=False, session=session, timeout=15)
        if isinstance(d1d.columns, pd.MultiIndex): d1d.columns = d1d.columns.get_level_values(0)
        
        # Tải nến 15m (7 ngày)
        d15m = yf.download(symbol, period='7d', interval='15m', progress=False, session=session, timeout=15)
        if isinstance(d15m.columns, pd.MultiIndex): d15m.columns = d15m.columns.get_level_values(0)

        return {"1h": d1h, "1d": d1d, "15m": d15m}
    except: return None

def process_and_resample(base_data, tf):
    """Hàm gộp nến và tính toán cho 12 khung thời gian"""
    try:
        rule_map = {
            '15m':'15min', '30m':'30min', '1h':'1h', '2h':'2H', '4h':'4H', 
            '8h':'8H', '12h':'12H', '1d':'1D', '3d':'3D', '1w':'W-MON', 
            '1M':'ME', '3M':'3ME'
        }
        # Chọn nguồn dữ liệu mồi
        if 'm' in tf: source = "15m"
        elif any(x in tf for x in ['h', 'H']): source = "1h"
        else: source = "1d"
        
        df = base_data[source].copy()
        if df.empty: return None

        # Thực hiện gộp nến nếu cần
        if tf not in ['15m', '1h', '1d']:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v109</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Tải khối dữ liệu mồi
        base = get_master_data(asset['symbol'])
        
        if base and not base['1h'].empty:
            live_p = float(base['1h']['Close'].iloc[-1])
            with st.expander(f"💠 {asset['name']} | Giá HT: {live_p:,.2f}", expanded=True):
                data_rows = []
                for tf in TIMEFRAMES:
                    # Chặn khung nhỏ cho VN-INDEX
                    if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h']): continue
                    
                    df_ind = process_and_resample(base, tf)
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        p_val, r, r9, r45 = last['Close'], last['rsi'], last['rsi9'], last['rsi45']
                        
                        if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                        elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                        elif r9 > r > r45: r_stat = "🟠 CHỈNH (-)"
                        elif r45 > r > r9: r_stat = "🔵 HỒI (+)"
                        else: r_stat = "🟡 YẾU"
                        
                        wave = "🟢 TĂNG" if p_val > last['ma20'] else "🔴 GIẢM"
                        data_rows.append({"KHUNG": tf.upper(), "SÓNG": wave, "RSI 9/45": r_stat, "RSI VAL": int(r), "GIÁ NẾN": f"{p_val:,.1f}"})
                
                if data_rows: st.table(pd.DataFrame(data_rows))
        else:
            st.error(f"❌ Nguồn dữ liệu {asset['name']} bị chặn IP. Đang tự động kết nối lại...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
