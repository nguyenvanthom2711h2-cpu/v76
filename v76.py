import streamlit as st
import yfinance as yf
from vnstock.api.quote import Quote
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
    {"name": "BITCOIN", "symbol": "BTC-USD", "source": "yahoo"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]
TIMEFRAMES = ['1h', '4h', '1d', '1w', '1m']

st.set_page_config(page_title="Pro Trade Dashboard v119", layout="wide")

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (CHUẨN TRADINGVIEW)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # SMA 20, 50
        df['ma20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['ma50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        df['ma10'] = df['Close'].rolling(window=10, min_periods=1).mean()
        
        # RSI Wilder's (RMA)
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
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP (KHÔNG TRÙNG SỐ)
# ==========================================
def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    logic = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
    return df.resample(rule).agg(logic).dropna()

@st.cache_data(ttl=60)
def fetch_data_v119(name, symbol, source, tf):
    """Tách biệt cache theo từng cặp tài sản và khung thời gian"""
    try:
        # A. XỬ LÝ VN-INDEX QUA VNSTOCK NỘI ĐỊA
        if source == "vnstock":
            try:
                q = Quote(symbol=symbol, source='VCI')
                # Nếu là khung lớn, tải nến ngày rồi gộp
                if tf in ['1d', '1w', '1m']:
                    df = q.history(start='2015-01-01', interval='1D')
                else: # Khung 1h, 4h
                    df = q.history(start=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'), interval='1H')
                
                if df is None or df.empty: raise Exception("Vnstock Empty")
                df = df.rename(columns={'time':'Date','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
                df.set_index('Date', inplace=True)
            except:
                # Fallback sang Yahoo nếu Vnstock lỗi
                df = yf.download('^VNINDEX', period='max', interval='1d', progress=False)
        
        # B. XỬ LÝ BTC & VÀNG QUA YAHOO
        else:
            if 'h' in tf: fetch_tf, period = '1h', '730d'
            else: fetch_tf, period = '1d', 'max'
            df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)

        if df is None or df.empty: return None

        # C. LOGIC GỘP NẾN CHÍNH XÁC
        if tf == '4h': df = resample_ohlc(df, '4H')
        elif tf == '1w': df = resample_ohlc(df, 'W-MON')
        elif tf == '1m': df = resample_ohlc(df, 'ME')

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
    color = 'white'
    if val in ["TĂNG", "HỒI (+)"]: color = "#00ff88"
    elif val in ["GIẢM", "CHỈNH (-)"]: color = "#ff4444"
    elif val == "YẾU": color = "#f1c40f"
    return f'color: {color}; font-weight: bold'

def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🏆 Master Trade Dashboard v119</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Giờ cập nhật (VN): <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            # Lấy giá hiện tại cho Bitcoin/Vàng từ Yahoo nến 1m cho nhạy
            live_p = get_live_price(asset['symbol'] if asset['name'] != 'VN-INDEX' else '^VNINDEX')
            live_p_str = f"{live_p:,.1f}" if live_p else "---"
            
            data_rows = []
            for tf in TIMEFRAMES:
                df = fetch_data_v119(asset['name'], asset['symbol'], asset['source'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    # Chỉ dùng giá live cho khung 1H để đồng bộ
                    p_val = live_p if (tf == '1h' and live_p) else last['Close']
                    r, r9, r45 = last['rsi_val'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "TĂNG"
                    elif r < r9 and r < r45: r_stat = "GIẢM"
                    elif r > r45 and r < r9: r_stat = "CHỈNH (-)"
                    elif r < r45 and r > r9: r_stat = "HỒI (+)"
                    else: r_stat = "YẾU"
                    
                    wave = "TĂNG" if p_val > last['ma20'] else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": wave,
                        "RSI 9/45": r_stat,
                        "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM",
                        "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                        "RSI": int(r),
                        "Giá HT": f"{p_val:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá: {live_p_str}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} không thể kết nối dữ liệu lúc này.", state="error")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
