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
    {"name": "BITCOIN", "symbol": "BTC-USD", "source": "yahoo"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "source": "yahoo"}
]

# Danh sách khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v110", layout="wide")

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
# 3. LẤY DỮ LIỆU ĐA NGUỒN (FIX VN-INDEX)
# ==========================================
@st.cache_data(ttl=60)
def get_asset_data(symbol, tf):
    try:
        # Đặc trị VN-INDEX: Yahoo chỉ có nến Ngày
        if symbol == "^VNINDEX" and any(x in tf for x in ['m', 'h', 'H']):
            return None # Không quét khung nhỏ cho VNI để tránh lỗi

        # Xác định khung gốc để tải
        if 'm' in tf:
            fetch_tf, period = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']):
            fetch_tf, period = '1h', '730d'
        else:
            fetch_tf, period = '1d', 'max'

        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False, timeout=15)
        if df.empty: return None
        
        # Sửa lỗi tiêu đề nhiều tầng của Yahoo mới
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df.index = pd.to_datetime(df.index)

        # Logic gộp nến (Resampling)
        rule_map = {
            '2h':'2H', '4h':'4H', '8h':'8H', '12h':'12H', 
            '3d':'3D', '1w':'W-MON', '1M':'ME', '3M':'3ME'
        }
        
        if tf in rule_map and tf != fetch_tf:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v110</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật thực: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        data_rows = []
        # Lấy giá hiện tại từ khung nến ngày để làm tiêu đề
        df_price = get_asset_data(asset['symbol'], '1d')
        live_p = df_price['Close'].iloc[-1] if df_price is not None else 0
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {live_p:,.2f}", expanded=True):
            sync_list = []
            for tf in TIMEFRAMES:
                df = get_asset_data(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = last['Close']
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat, r_code = "🟢 TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "🔴 GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "🟠 CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "🔵 HỒI (+)", 0
                    else: r_stat, r_code = "🟡 YẾU", 0
                    
                    # Xét đồng thuận để hiện (↑) (↓)
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        if r_code == 1 and prev['code'] == 1: agreement = "MUA (↑)"
                        elif r_code == -1 and prev['code'] == -1: agreement = "BÁN (↓)"
                    
                    sync_list.append({"tf": tf, "code": r_code})
                    wave = "🟢 TĂNG" if p_val > last['ma20'] else "🔴 GIẢM"
                    
                    data_rows.append({
                        "KHUNG": tf.upper(),
                        "SÓNG": wave,
                        "ĐỒNG THUẬN": agreement,
                        "RSI 9/45": r_stat,
                        "RSI": int(r),
                        "GIÁ NẾN": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                st.table(pd.DataFrame(data_rows))
            else:
                st.warning(f"⚠️ Đang chờ dữ liệu cho {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
