import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import requests
import warnings
import pytz

# Tắt cảnh báo
warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

# FIX LỖI MÚI GIỜ: Asia/Ho_Chi_Minh
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Spot)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Real-time Dashboard v96", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (CÔNG NGHỆ MỚI)
# ==========================================
def get_live_price(symbol):
    """Lấy giá trực tiếp bằng cách tải nến 1 phút mới nhất"""
    try:
        # Tải nến 1 phút để lấy giá đóng cửa tức thời
        df = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=10)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df['Close'].iloc[-1]
    except:
        return None
    return None

# ==========================================
# 3. TÍNH TOÁN CHỈ BÁO
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
# 4. LẤY DỮ LIỆU LỊCH SỬ
# ==========================================
@st.cache_data(ttl=60) # Chỉ lưu 1 phút để cập nhật liên tục
def fetch_history(symbol, tf):
    try:
        yf_map = {'1h':'1h', '1d':'1d', '1w':'1wk', '1M':'1mo'}
        fetch_tf = yf_map.get(tf, '1d')
        period = '730d' if fetch_tf == '1h' else 'max'
        
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if tf == '4h':
            df = df.resample('4H').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v96</h1>", unsafe_allow_html=True)
    
    # Hiển thị thời gian Việt Nam chuẩn
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Lấy giá Live cho từng asset
        live_p = get_live_price(asset['symbol'])
        live_p_str = f"{live_p:,.2f}" if live_p else "---"
        
        st.subheader(f"💠 {asset['name']} | Giá HT: {live_p_str}")
        
        data_rows = []
        for tf in TIMEFRAMES:
            df = fetch_history(asset['symbol'], tf)
            if df is not None:
                last = df.iloc[-1]
                # Ở khung 1h, dùng giá Live để chỉ báo nhảy theo thực tế
                p_display = live_p if (tf == '1h' and live_p) else last['Close']
                
                r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                
                # Trạng thái RSI
                if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                elif r9 > r > r45: r_stat = "🟠 CHỈNH (-)"
                elif r45 > r > r9: r_stat = "🔵 HỒI (+)"
                else: r_stat = "🟡 YẾU"
                
                # Trạng thái Sóng
                wave = "🟢 TĂNG" if p_display > last['ma20'] else "🔴 GIẢM"
                
                data_rows.append({
                    "KHUNG": tf.upper(),
                    "SÓNG": wave,
                    "RSI 9/45": r_stat,
                    "RSI VAL": int(r),
                    "GIÁ NẾN": f"{p_display:,.1f}"
                })
        
        if data_rows:
            st.table(pd.DataFrame(data_rows))
        else:
            st.warning(f"🔄 Đang tải dữ liệu cho {asset['name']}...")

    # Tự động reload sau 30 giây
    time.sleep(30)
    st.rerun()

if __name__ == "__main__":
    main()
