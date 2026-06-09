import streamlit as st
import ccxt
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
    {"name": "BITCOIN", "symbol": "BTC/USDT", "source": "binance"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "^VNINDEX", "source": "yahoo"}
]

# Đầy đủ 12 khung thời gian
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']

st.set_page_config(page_title="Master Trade Dashboard v100", layout="wide")
exchange = ccxt.binance({'timeout': 10000, 'enableRateLimit': True})

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RSI RMA & MA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy()
        df['ma20'] = df['c'].rolling(window=20).mean()
        df['ma50'] = df['c'].rolling(window=50, min_periods=10).mean()
        delta = df['c'].diff()
        gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=1, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9, min_periods=1).mean()
        df['rsi45'] = df['rsi'].rolling(45, min_periods=1).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU CHUẨN XÁC
# ==========================================
def get_data(asset, tf):
    try:
        if asset['source'] == "binance":
            # Binance có sẵn hầu hết các khung. 3M gộp từ 1M.
            limit = 1000 if tf in ['1w', '1M'] else 500
            fetch_tf = '1M' if tf == '3M' else tf
            bars = exchange.fetch_ohlcv(asset['symbol'], fetch_tf, limit=limit)
            df = pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
            if tf == '3M':
                df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                df = df.set_index('ts').resample('3ME').agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
            return df
            
        elif asset['source'] == "yahoo":
            yf_map = {'15m':'15m','30m':'30m','1h':'1h','1d':'1d','1w':'1wk','1M':'1mo'}
            fetch_tf = yf_map.get(tf, '1h' if 'h' in tf else '1d')
            period = 'max' if any(x in tf for x in ['d', 'w', 'M']) else '7d' if 'm' in tf else '730d'
            df = yf.download(asset['symbol'], period=period, interval=fetch_tf, progress=False)
            if df.empty: return None
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.reset_index().rename(columns={df.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
            
            # Gộp nến cho khung Yahoo thiếu
            if tf in ['2h','4h','8h','12h','3d','3M']:
                rule = tf.upper().replace('M','ME')
                df['ts'] = pd.to_datetime(df['ts'])
                df = df.set_index('ts').resample(rule).agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
            return df
    except: return None

# ==========================================
# 4. GIAO DIỆN CHÍNH
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Real-time Master Dashboard v100</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        st.subheader(f"💠 {asset['name']}")
        data_rows = []
        
        # Thử lấy giá hiện tại mới nhất
        current_price = 0
        
        for tf in TIMEFRAMES:
            df_raw = get_data(asset, tf)
            df = calculate_indicators(df_raw)
            if df is not None:
                last = df.iloc[-1]
                p = last['c']
                if current_price == 0: current_price = p # Lấy giá khung nhỏ nhất làm giá hiện tại
                
                r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                if r > r9 and r > r45: r_stat = "🟢 TĂNG"
                elif r < r9 and r < r45: r_stat = "🔴 GIẢM"
                elif r > r45 and r < r9: r_stat = "🟠 CHỈNH (-)"
                elif r < r45 and r > r9: r_stat = "🔵 HỒI (+)"
                else: r_stat = "🟡 YẾU"
                
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
            st.warning(f"🔄 Đang tải dữ liệu {asset['name']}...")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
