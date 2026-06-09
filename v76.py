import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz

# Tắt cảnh báo
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Spot)", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Real-time Trade Dashboard v99", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. LẤY DỮ LIỆU & GIÁ THỰC (FIX CACHE)
# ==========================================
def get_live_price(symbol):
    """Lấy giá 1 phút mới nhất - Xử lý Multi-Index"""
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=10)
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data['Close'].iloc[-1]
    except: return None
    return None

@st.cache_data(ttl=30) # Lưu 30 giây để cập nhật giá nhanh
def fetch_history(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        f_tf = yf_map.get(tf, '1h' if 'h' in tf else '1d')
        period = '730d' if f_tf == '1h' else 'max'
        df = yf.download(symbol, period=period, interval=f_tf, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if tf in ['4h', '8h', '12h']:
            df = df.resample(tf.upper()).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v99</h1>", unsafe_allow_html=True)
    
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Lấy giá Live cho từng asset
        live_p = get_live_price(asset['symbol'])
        p_str = f"{live_p:,.2f}" if live_p else "---"
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {p_str}", expanded=True):
            data_rows = []
            for tf in TIMEFRAMES:
                if asset['name'] == "VN-INDEX" and tf in ['1h', '4h']: continue
                
                df = fetch_history(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = live_p if (tf == '1h' and live_p) else last['Close']
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                    elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                    elif r > r45 and r < r9: r_stat = "🟠 CHỈNH (-)"
                    elif r < r45 and r > r9: r_stat = "🔵 HỒI (+)"
                    else: r_stat = "🟡 YẾU"
                    
                    wave = "🟢 TĂNG" if p_val > last['ma20'] else "🔴 GIẢM"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "RSI VAL": int(r),
                        "GIÁ NẾN": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.warning(f"🔄 Đang kết nối dữ liệu {asset['name']}...")

    # Tự động refresh sau 30 giây
    time.sleep(30)
    st.rerun()

if __name__ == "__main__":
    main()
