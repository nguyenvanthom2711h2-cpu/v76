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
    {"name": "VÀNG", "symbol": "GC=F"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# Danh sách khung thời gian khớp theo bảng yêu cầu
TIMEFRAMES = ['1h', '4h', '8h', '12h', '1d', '3d', '1w', '1m']

st.set_page_config(page_title="Master Trade Dashboard", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # MA chuẩn
        df['ma10'] = df['Close'].rolling(window=10).mean()
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        # RSI Wilder's
        delta = df['Close'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐA TẦNG
# ==========================================
@st.cache_data(ttl=30)
def get_data(symbol, tf):
    try:
        # Xác định fetch gốc
        if 'h' in tf: fetch_tf, period = '1h', '730d'
        else: fetch_tf, period = '1d', 'max'
            
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=15)
        if df.empty: return None
        
        # Resample cho các khung trung gian
        rule_map = {'4h':'4H', '8h':'8H', '12h':'12H', '3d':'3D', '1w':'W-MON', '1m':'ME'}
        if tf in rule_map:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

def get_live_price(symbol):
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        return float(data['Close'].iloc[-1])
    except: return None

# ==========================================
# 4. GIAO DIỆN WEB & TÔ MÀU
# ==========================================
def style_table(val):
    color = 'white'
    if val in ["TĂNG", "HỒI (+)"]: color = "#2ecc71" # Xanh lá
    elif val in ["GIẢM", "CHỈNH (-)"]: color = "#e74c3c" # Đỏ
    elif val == "YẾU": color = "#f1c40f" # Vàng
    return f'color: {color}; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: left;'>🏆 Master Trade Dashboard</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S')
    st.write(f"Cập nhật lúc: {now_vn}")

    for asset in LIST_ASSETS:
        st.markdown(f"### 💠 {asset['name']}")
        
        # Lấy giá hiện tại một lần cho cả bảng
        live_p = get_live_price(asset['symbol'])
        live_p_str = f"{live_p:,.1f}" if live_p else "---"
        
        data_rows = []
        for tf in TIMEFRAMES:
            # Đặc trị VN-Index (Không lấy khung giờ để tránh lỗi Yahoo)
            if asset['name'] == "VN-INDEX" and 'h' in tf: continue
            
            df = get_data(asset['symbol'], tf)
            if df is not None:
                last = df.iloc[-1]
                p_val = live_p if (tf == '1h' and live_p) else last['Close']
                r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                
                # Logic RSI 9/45 (Đúng chuẩn Hồi/Chỉnh)
                if r > r9 and r > r45: r_stat = "TĂNG"
                elif r < r9 and r < r45: r_stat = "GIẢM"
                elif r > r45 and r < r9: r_stat = "CHỈNH (-)"
                elif r < r45 and r > r9: r_stat = "HỒI (+)"
                else: r_stat = "YẾU"
                
                rows_data = {
                    "Khung": tf.upper(),
                    "Sóng": "TĂNG" if p_val > last['ma20'] else "GIẢM",
                    "RSI 9/45": r_stat,
                    "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                    "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                    "RSI": int(r),
                    "Giá HT": live_p_str # Hiển thị giá đồng nhất như trong hình
                }
                data_rows.append(rows_data)
        
        if data_rows:
            df_display = pd.DataFrame(data_rows)
            # Áp dụng màu sắc cho từng cột
            st.table(df_display.style.applymap(style_table, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    # Tự động refresh sau 60s
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
