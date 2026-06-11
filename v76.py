import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
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

# 12 Khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Pro Trade Dashboard v146", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (RMA WILDER'S CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 10: return None
    try:
        df = df.copy()
        # Ép tiêu đề cột về 1 tầng duy nhất (Sửa lỗi Yahoo 2025)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        col = 'Close' if 'Close' in df.columns else df.columns[0]
        
        df['ma10'] = df[col].rolling(10, min_periods=1).mean()
        df['ma20'] = df[col].rolling(20, min_periods=1).mean()
        df['ma50'] = df[col].rolling(50, min_periods=1).mean()
        
        delta = df[col].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi_val'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP (CHỐNG LẶP SỐ)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    # Chỉ lấy các cột thực sự tồn tại
    actual_logic = {k: v for k, v in logic.items() if k in df.columns}
    return df.resample(rule).agg(actual_logic).dropna()

@st.cache_data(ttl=60) # Cache theo (symbol + tf) để không bị trùng số
def fetch_data_v146(symbol, tf):
    try:
        # 1. Xác định interval gốc
        if 'm' in tf and '1m' not in tf: f_tf, p = tf, '7d'
        elif any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']): f_tf, p = '1h', '730d'
        else: f_tf, p = '1d', 'max'
            
        # 2. Tải dữ liệu
        df = yf.download(symbol, period=p, interval=f_tf, progress=False, timeout=20)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # 3. Gộp nến cho khung trung gian
        rule_map = {'30m':'30min','2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1m':'ME','3m':'3ME'}
        if tf in rule_map and tf != f_tf:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
    except: return None

def get_live_price(symbol):
    try:
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        return float(data['Close'].iloc[-1])
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold'
    if val == "YẾU": return 'color: #f1c40f; font-weight: bold'
    return ''

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v146</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): {now_vn}</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            live_p = get_live_price(asset['symbol'])
            live_p_str = f"{live_p:,.1f}" if live_p else "---"
            
            data_rows = []
            for tf in TIMEFRAMES:
                # Yahoo VN-INDEX ko có khung giờ
                if asset['name'] == "VN-INDEX" and any(x in tf for x in ['m', 'h', 'H']): continue
                
                df_ind = fetch_data_v146(asset['symbol'], tf)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    p_val = float(last['Close'])
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    
                    if r > r9 and r > r45: r_stat = "TĂNG"
                    elif r < r9 and r < r45: r_stat = "GIẢM"
                    elif r9 > r > r45: r_stat = "CHỈNH (-)"
                    elif r45 > r > r9: r_stat = "HỒI (+)"
                    else: r_stat = "YẾU"
                    
                    wave = "TĂNG" if p_val > float(last['ma20']) else "GIẢM"
                    p50 = "TĂNG" if p_val > float(last['ma50']) else "GIẢM"
                    m1020 = "TĂNG" if float(last['ma10']) > float(last['ma20']) else "GIẢM"

                    data_rows.append({
                        "Khung": tf.upper(), "Sóng": wave, "RSI 9/45": r_stat,
                        "P/MA50": p50, "MA 10/20": m1020,
                        "RSI": int(r), "Giá nến": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {live_p_str}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text))
            else:
                status.update(label=f"❌ {asset['name']} không có dữ liệu.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
