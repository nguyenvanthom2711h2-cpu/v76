import streamlit as st
import ccxt
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
import time
import telebot
import contextlib
import os, sys

# --- CẤU HÌNH ---
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC/USDT", "source": "binance"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]
TIMEFRAMES = ['1h', '4h', '8h', '12h', '1d', '3d', '1w', '1M']

# Cấu hình trang Web
st.set_page_config(page_title="Master Trade Dashboard", layout="wide")
bot = telebot.TeleBot(TOKEN)
exchange = ccxt.binance()

@st.cache_data(ttl=60) # Lưu bộ nhớ đệm 60s
def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    df = df.copy()
    df['ma10'] = df['c'].rolling(10).mean()
    df['ma20'] = df['c'].rolling(20).mean()
    df['ma50'] = df['c'].rolling(50, min_periods=1).mean()
    delta = df['c'].diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
    df['rsi9'] = df['rsi'].rolling(9).mean()
    df['rsi45'] = df['rsi'].rolling(45).mean()
    return df

def get_data(asset, tf):
    try:
        if asset['source'] == "binance":
            bars = exchange.fetch_ohlcv(asset['symbol'], tf, limit=500)
            return pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
        elif asset['source'] == "yahoo":
            yf_map = {'1h':'1h','1d':'1d'}
            f_tf = '1h' if 'h' in tf else '1d'
            df = yf.download(asset['symbol'], period='max', interval=f_tf, progress=False)
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.rename(columns={df.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
            if tf in ['4h','8h','12h','3d','1w','1M']:
                df['ts'] = pd.to_datetime(df['ts'])
                df = df.set_index('ts').resample(tf.upper().replace('M','ME')).agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
            return df
        elif asset['source'] == "vnstock":
            q = Quote(symbol='VNINDEX', source='VCI')
            df = q.history(start='2015-01-01', interval='1D' if 'd' in tf or 'w' in tf or 'M' in tf else '1H')
            df = df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
            return df
    except: return None

# Hàm tô màu cho bảng Web
def color_df(val):
    if val == "TĂNG" or val == "HỒI (+)": color = '#2ecc71' # Xanh lá
    elif val == "GIẢM" or val == "CHỈNH (-)": color = '#e74c3c' # Đỏ
    elif val == "YẾU": color = '#f1c40f' # Vàng
    else: color = 'white'
    return f'color: {color}; font-weight: bold'

def main():
    st.title("🏆 Master Trade Dashboard")
    st.write(f"Cập nhật lúc: {datetime.now().strftime('%H:%M:%S')}")
    
    for asset in LIST_ASSETS:
        st.subheader(f"💠 {asset['name']}")
        rows = []
        for tf in TIMEFRAMES:
            df_raw = get_data(asset, tf)
            df_ind = calculate_indicators(df_raw)
            if df_ind is not None:
                last = df_ind.iloc[-1]
                curr_p = last['c']
                r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                
                if r > r9 and r > r45: r_stat = "TĂNG"
                elif r < r9 and r < r45: r_stat = "GIẢM"
                elif r9 > r > r45: r_stat = "CHỈNH (-)"
                elif r45 > r > r9: r_stat = "HỒI (+)"
                else: r_stat = "YẾU"

                rows.append({
                    "Khung": tf.upper(),
                    "Sóng": "TĂNG" if curr_p > last['ma20'] else "GIẢM",
                    "RSI 9/45": r_stat,
                    "P/MA50": "TĂNG" if curr_p > last['ma50'] else "GIẢM",
                    "MA 10/20": "TĂNG" if last['ma10'] > last['ma20'] else "GIẢM",
                    "RSI": int(r),
                    "Giá HT": f"{curr_p:,.1f}"
                })
        
        if rows:
            display_df = pd.DataFrame(rows)
            # Áp dụng màu sắc và hiển thị bảng
            st.table(display_df.style.applymap(color_df, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))

    # Tự động reload trang sau 60s
    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
