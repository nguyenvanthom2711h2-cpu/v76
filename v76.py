import streamlit as st
import yfinance as yf
from vnstock.api.quote import Quote # Sử dụng API v4
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD"},
    {"name": "VÀNG (Thế giới)", "symbol": "XAUUSD=X"},
    {"name": "VN-INDEX", "symbol": "VNINDEX"} 
]

# Đầy đủ 12 khung thời gian yêu cầu
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v108", layout="wide")

# ==========================================
# 2. HÀM TÍNH TOÁN KỸ THUẬT (RSI RMA & MA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        df = df.copy()
        # MA chuẩn (Simple Moving Average)
        df['ma20'] = df['Close'].rolling(window=20).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=10).mean()
        
        # RSI Wilder's chuẩn (RMA)
        delta = df['Close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        
        # SỬA LỖI: Chuyển RSI9 và RSI45 sang EMA (ewm) để mượt mà và chính xác như TradingView
        df['rsi9'] = df['rsi'].ewm(span=9, adjust=False).mean()
        df['rsi45'] = df['rsi'].ewm(span=45, adjust=False).mean()
        return df
    except: return None

# ==========================================
# 3. MÁY TẢI DỮ LIỆU ĐA NGUỒN (FIX VN-INDEX GOOGLE CLOUD)
# ==========================================
def resample_data(df, rule):
    if df is None or len(df) < 2: return None
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).apply(logic).dropna().reset_index()

@st.cache_data(ttl=30)
def fetch_and_resample_v108(symbol, tf):
    try:
        # A. XỬ LÝ VN-INDEX QUA KHUNG KBS (KHÔNG BỊ CHẶN IP GOOGLE CLOUD)
        if symbol == "VNINDEX":
            # Dùng nguồn KBS thay vì VCI để tránh bị chặn IP từ Google Cloud
            q = Quote(symbol='VNINDEX', source='KBS') 
            v_tf = '1H' if 'h' in tf.lower() else '1D'
            df_raw = q.history(start='2010-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=v_tf)
            if df_raw is None or df_raw.empty: return None
            df = df_raw.rename(columns={'time':'ts','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
            if tf in ['3d', '1w', '1M', '3M']:
                df = resample_data(df, {'3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}[tf])
            return calculate_indicators(df)

        # B. XỬ LÝ BITCOIN & VÀNG (YAHOO FINANCE)
        else:
            yf_map = {'15m':'15m','30m':'30m','1h':'1h','1d':'1d'}
            fetch_tf = '1h' if 'h' in tf else ('1d' if any(x in tf for x in ['d','w','M']) else tf)
            period = '7d' if 'm' in tf else ('730d' if 'h' in tf else 'max')
            
            df = yf.download(symbol, period=period, interval=yf_map.get(fetch_tf, fetch_tf), progress=False, timeout=15)
            if df.empty: return None
            
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.rename(columns={df.columns[0]:'ts'})
            
            # Gộp nến cho các khung trung gian
            if tf in ['4h','8h','12h','3d','1w','1M','3M']:
                rules = {'4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
                df = resample_data(df, rules[tf])
                
            return calculate_indicators(df)
    except: return None

def get_live_price(symbol):
    try:
        # Nếu là VNINDEX, lấy giá từ vnstock KBS
        if symbol == "VNINDEX":
            q = Quote(symbol='VNINDEX', source='KBS')
            df = q.history(start=(datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'), interval='1D')
            return float(df['close'].iloc[-1])
        # Bitcoin/Vàng lấy từ Yahoo 1m
        data = yf.download(symbol, period='1d', interval='1m', progress=False, timeout=5)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        return float(data['Close'].iloc[-1])
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v108</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ Việt Nam: <b>{now_vn}</b> (Tự động tải lại sau 60s)</p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        live_p = get_live_price(asset['symbol'])
        p_title = f"{live_p:,.2f}" if live_p is not None else "---"
        
        with st.expander(f"💠 {asset['name']} | Giá HT: {p_title}", expanded=True):
            data_rows = []
            for tf in TIMEFRAMES:
                # Chặn khung giờ cho VN-INDEX
                if asset['name'] == "VN-INDEX" and ('m' in tf or 'h' in tf): continue
                
                df = fetch_and_resample_v108(asset['symbol'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p_val = live_p if (tf in ['15m', '30m', '1h'] and live_p is not None) else last['Close']
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    # Trạng thái RSI (Khớp chuẩn mượt mà)
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
                st.warning(f"🔄 Đang đồng bộ hóa dữ liệu cho {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
