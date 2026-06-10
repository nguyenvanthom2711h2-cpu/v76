import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Thế giới)", "symbol": "XAUUSD=X"}, # Đổi sang Vàng Spot chuẩn TradingView
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# 12 Khung thời gian đầy đủ
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v102", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA WILDER'S CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Công thức RSI Wilder's chuẩn (RMA) dùng alpha = 1/period
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. MÁY TẢI DỮ LIỆU TỐI ƯU
# ==========================================
@st.cache_data(ttl=30) # Lưu 30 giây để cập nhật giá nhanh
def get_unified_data(symbol, tf):
    try:
        # Map khung giờ Yahoo
        if any(x in tf for x in ['m', 'h', 'H']):
            base_tf = '1h' if 'h' in tf or 'H' in tf else tf
            period = '7d' if 'm' in tf else '730d'
        else:
            base_tf = '1d'
            period = 'max'

        df = yf.download(symbol, period=period, interval=base_tf, progress=False, timeout=10)
        
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df.index = pd.to_datetime(df.index)
        
        # LOGIC GỘP NẾN (RESAMPLE) - SỬA LỖI THIẾU KHUNG 4H, 8H, 12H
        rule_map = {
            '2h': '2H', '4h': '4H', '8h': '8H', '12h': '12H', 
            '3d': '3D', '1w': 'W-MON', '1M': 'ME', '3M': '3ME'
        }
        
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).apply(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v102</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b> (Tự động tải lại sau 60s)</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        st.subheader(f"💠 {asset['name']}")
        data_rows = []
        
        for tf in TIMEFRAMES:
            # Đặc trị VN-INDEX: Yahoo ko cung cấp nến Giờ
            if asset['name'] == "VN-INDEX" and 'h' in tf: continue
            
            df = get_unified_data(asset['symbol'], tf)
            if df is not None:
                last = df.iloc[-1]
                p, r, r9, r45 = last['Close'], last['rsi'], last['rsi9'], last['rsi45']
                
                # Trạng thái RSI
                if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                elif r9 > r > r45: r_stat = "🟠 CHỈNH (-)"
                elif r45 > r > r9: r_stat = "🔵 HỒI (+)"
                else: r_stat = "🟡 YẾU"
                
                # Trạng thái Sóng
                wave = "🟢 TĂNG" if p > last['ma20'] else "🔴 GIẢM"
                
                data_rows.append({
                    "KHUNG": tf.upper(),
                    "SÓNG": wave,
                    "RSI 9/45": r_stat,
                    "RSI VAL": int(r),
                    "GIÁ NẾN": f"{p:,.1f}"
                })
        
        if data_rows:
            st.table(pd.DataFrame(data_rows))
        else:
            st.warning(f"🔄 Đang kết nối dữ liệu {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
