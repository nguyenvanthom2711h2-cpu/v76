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
    {"name": "VÀNG", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX"}
]

# 12 Khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v108", layout="wide")

# ==========================================
# 2. TÍNH TOÁN KỸ THUẬT (RMA WILDER'S)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TẢI DỮ LIỆU TẬP TRUNG (GIẢM SỐ LẦN GỌI API)
# ==========================================
@st.cache_data(ttl=60)
def fetch_base_data(symbol):
    """Tải dữ liệu mồi (1H và 1D) 1 lần duy nhất cho mỗi tài sản"""
    try:
        # Tải nến 1H (cho các khung giờ và phút)
        df_1h = yf.download(symbol, period='730d', interval='1h', progress=False, timeout=15)
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.get_level_values(0)
        
        # Tải nến 1D (cho các khung ngày và tháng)
        df_1d = yf.download(symbol, period='max', interval='1d', progress=False, timeout=15)
        if isinstance(df_1d.columns, pd.MultiIndex): df_1d.columns = df_1d.columns.get_level_values(0)
        
        return {"1h": df_1h, "1d": df_1d}
    except: return None

def process_tf(base_data, tf):
    """Gộp nến từ dữ liệu mồi và tính toán chỉ báo"""
    try:
        rule_map = {
            '15m': '15min', '30m': '30min', '1h': '1h', '2h': '2H', '4h': '4H', 
            '8h': '8H', '12h': '12H', '1d': '1D', '3d': '3D', '1w': 'W-MON', 
            '1M': 'ME', '3M': '3ME'
        }
        
        # Chọn nguồn dữ liệu gốc
        source = "1h" if any(x in tf for x in ['m', 'h', 'H']) else "1d"
        df = base_data[source].copy()
        if df.empty: return None

        # Tiến hành gộp nến (Resample)
        if tf != source:
            logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
            df = df.resample(rule_map[tf]).agg(logic).dropna()
            
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Trade Dashboard v108</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật thực: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        # Tải dữ liệu mồi
        base = fetch_base_data(asset['symbol'])
        
        if base and not base['1h'].empty:
            # Lấy giá HT từ nến 1H mới nhất
            live_p = float(base['1h']['Close'].iloc[-1])
            p_title = f"{live_p:,.2f}"
            
            with st.expander(f"💠 {asset['name']} | Giá HT: {p_title}", expanded=True):
                data_rows = []
                for tf in TIMEFRAMES:
                    # VN-INDEX bỏ qua khung giờ/phút
                    if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h']): continue
                    
                    df_ind = process_tf(base, tf)
                    if df_ind is not None:
                        last = df_ind.iloc[-1]
                        p_val = last['Close']
                        r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                        
                        # Trạng thái
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
            st.error(f"❌ Không thể kết nối dữ liệu cho {asset['name']}. Vui lòng chờ Yahoo Finance mở khóa IP.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
