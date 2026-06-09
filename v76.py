import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import requests
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "yf_symbol": "BTC-USD"},
    {"name": "VÀNG (Spot)", "symbol": "XAUUSD=X", "yf_symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "yf_symbol": "^VNINDEX"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1M']

st.set_page_config(page_title="Trade Master Live v95", layout="wide")

# ==========================================
# 2. HÀM LẤY GIÁ LIVE (KHÔNG CACHE - CẬP NHẬT TỨC THÌ)
# ==========================================
def get_live_price(symbol):
    """Lấy giá hiện tại mới nhất từ Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        # Lấy giá từ lần khớp lệnh gần nhất (fast quote)
        price = ticker.fast_info['last_price']
        return price
    except:
        try:
            # Fallback nếu fast_info lỗi
            df = yf.download(symbol, period='1d', interval='1m', progress=False)
            return df['Close'].iloc[-1]
        except:
            return None

# ==========================================
# 3. TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
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
        # RSI chuẩn TradingView (EMA alpha=1/14)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 4. LẤY DỮ LIỆU LỊCH SỬ (DÙNG ĐỂ TÍNH RSI/MA)
# ==========================================
@st.cache_data(ttl=60) # Lưu 60 giây để tránh bị Yahoo chặn
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Trade Dashboard v95</h1>", unsafe_allow_html=True)
    
    # Cập nhật múi giờ Việt Nam
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Lấy giá Live trước để hiện tiêu đề
        live_p = get_live_price(asset['yf_symbol'])
        live_p_str = f"{live_p:,.2f}" if live_p else "Đang tải..."
        
        with st.expander(f"💠 {asset['name']} | Giá Live: {live_p_str}", expanded=True):
            data_rows = []
            for tf in TIMEFRAMES:
                df = fetch_history(asset['yf_symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    # Nếu khung 1h thì cập nhật giá Close cuối nến bằng giá Live để chỉ báo khớp thực tế
                    if tf == '1h' and live_p: p_val = live_p
                    else: p_val = last['Close']
                    
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                    elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                    else: r_stat = "🟡 YẾU"
                    
                    wave = "🟢 TĂNG" if p_val > last['ma20'] else "🔴 GIẢM"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "RSI 9/45": r_stat,
                        "GIÁ NẾN": f"{p_val:,.1f}",
                        "RSI": int(r)
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.warning(f"⚠️ Đang kết nối nguồn dữ liệu {asset['name']}...")

    # Tự động refresh sau 30 giây để cập nhật giá Live
    time.sleep(30)
    st.rerun()

if __name__ == "__main__":
    main()
