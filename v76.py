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
    {"name": "BITCOIN", "symbol": "BTC-USD", "fallback": "BTC-USD"},
    {"name": "VÀNG", "symbol": "GC=F", "fallback": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "fallback": "^VNINDEX"}
]

# Danh sách 12 khung thời gian cố định
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Pro Trade Dashboard v107", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (TỐI ƯU CHO KHUNG NHỎ)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 5:
        return None
    try:
        df = df.copy()
        # Tính MA với min_periods=1 để luôn hiện số
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        
        # RSI Wilder's chuẩn (RMA)
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except:
        return None

# ==========================================
# 3. LẤY DỮ LIỆU "SIÊU ĐA KHUNG"
# ==========================================
@st.cache_data(ttl=30)
def fetch_data_v107(symbol, tf, fallback):
    try:
        # Nhóm 1: Khung phút
        if 'm' in tf:
            df = yf.download(symbol, period='7d', interval=tf, progress=False, timeout=10)
        # Nhóm 2: Khung giờ (bao gồm 2h, 4h, 8h, 12h)
        elif 'h' in tf.lower() or tf in ['2h','4h','8h','12h']:
            df = yf.download(symbol, period='730d', interval='1h', progress=False, timeout=10)
        # Nhóm 3: Khung ngày trở lên
        else:
            df = yf.download(symbol, period='max', interval='1d', progress=False, timeout=10)

        if df is None or df.empty:
            df = yf.download(fallback, period='max', interval='1d', progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df.index = pd.to_datetime(df.index)

        # Map gộp nến
        rule_map = {'2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', '3d':'3D', '1w':'W-MON', '1M':'ME', '3M':'3ME'}
        if tf in rule_map and tf not in ['1h', '1d']:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except:
        return None

def get_price(symbol):
    try:
        d = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        return float(d['Close'].iloc[-1])
    except:
        return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v107</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        live_p = get_price(asset['symbol'])
        p_title = f"{live_p:,.2f}" if live_p else "---"
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {p_title}", expanded=True):
            data_rows = []
            for tf in TIMEFRAMES:
                # VNINDEX ko có nến phút/giờ trên Yahoo
                if asset['name'] == "VN-INDEX" and ('m' in tf or 'h' in tf): continue
                
                df = fetch_data_v107(asset['symbol'], tf, asset['fallback'])
                if df is not None:
                    last = df.iloc[-1]
                    p_val = live_p if (tf in ['15m', '30m', '1h'] and live_p) else last['Close']
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                    elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                    elif r9 > r > r45: r_stat = "🟠 CHỈNH (-)"
                    elif r45 > r > r9: r_stat = "🔵 HỒI (+)"
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
                st.info(f"🔄 Đang kết nối nguồn {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
