import streamlit as st
import ccxt
import yfinance as yf
from vnstock.api.quote import Quote
import pandas as pd
from datetime import datetime, timedelta
import time
import telebot
import warnings

warnings.filterwarnings("ignore")

# --- CẤU HÌNH ---
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC/USDT", "yf_symbol": "BTC-USD", "source": "binance"},
    {"name": "VÀNG", "symbol": "GC=F", "yf_symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "yf_symbol": "^VNINDEX", "source": "vnstock"}
]
TIMEFRAMES = ['1h', '4h', '8h', '12h', '1d', '3d', '1w', '1M']

# Cấu hình trang Web
st.set_page_config(page_title="Master Trade Dashboard", layout="wide")
bot = telebot.TeleBot(TOKEN)

# Khởi tạo exchange Binance
exchange = ccxt.binance({'timeout': 20000, 'enableRateLimit': True})

def calculate_indicators(df):
    if df is None or len(df) < 50: return None
    try:
        df = df.copy()
        df['ma10'] = df['c'].rolling(10).mean()
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=10).mean()
        delta = df['c'].diff()
        avg_gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi'].rolling(9).mean()
        df['rsi45'] = df['rsi'].rolling(45).mean()
        return df
    except: return None

def get_data_from_yahoo(symbol, tf):
    """Hàm lấy dữ liệu từ Yahoo Finance làm dự phòng"""
    yf_map = {'1h':'1h','1d':'1d'}
    fetch_tf = '1h' if 'h' in tf else '1d'
    period = '730d' if fetch_tf == '1h' else 'max'
    df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
    if df.empty: return None
    df = df.reset_index()
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={df.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
    if tf in ['4h','8h','12h','3d','1w','1M']:
        rule = tf.upper().replace('M','ME').replace('W','W-MON')
        df['ts'] = pd.to_datetime(df['ts'])
        df = df.set_index('ts').resample(rule).agg({'o':'first','h':'max','l':'min','c':'last','v':'sum'}).dropna().reset_index()
    return df

def get_data(asset, tf):
    # Thử lấy Bitcoin từ Binance trước
    if asset['name'] == "BITCOIN":
        try:
            bars = exchange.fetch_ohlcv(asset['symbol'], tf, limit=1000)
            return pd.DataFrame(bars, columns=['ts','o','h','l','c','v'])
        except Exception as e:
            # Nếu Binance lỗi/bị chặn IP -> Chuyển sang Yahoo Finance
            return get_data_from_yahoo(asset['yf_symbol'], tf)
            
    elif asset['source'] == "yahoo":
        return get_data_from_yahoo(asset['symbol'], tf)

    elif asset['source'] == "vnstock":
        try:
            q = Quote(symbol=asset['symbol'], source='VCI')
            df = q.history(start='2020-01-01', interval='1D' if 'd' in tf or 'w' in tf or 'M' in tf else '1H')
            return df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
        except: return None
    return None

def color_df(val):
    if val == "TĂNG": color = '#2ecc71'
    elif val == "GIẢM": color = '#e74c3c'
    elif val == "HỒI (+)": color = '#3498db'
    elif val == "CHỈNH (-)": color = '#e67e22'
    elif val == "YẾU": color = '#f1c40f'
    else: color = 'white'
    return f'color: {color}; font-weight: bold'

def main():
    st.title("🏆 Master Trade Dashboard v88")
    st.info("💡 Lưu ý: Nếu Binance bị chặn IP, hệ thống sẽ tự động dùng Yahoo Finance cho Bitcoin.")
    st.write(f"Cập nhật lúc: {datetime.now().strftime('%H:%M:%S')} (Tự động reload sau 60s)")
    
    for asset in LIST_ASSETS:
        st.subheader(f"💠 {asset['name']}")
        rows = []
        
        with st.status(f"Đang phân tích {asset['name']}...", expanded=False) as status:
            for tf in TIMEFRAMES:
                df_raw = get_data(asset, tf)
                df_ind = calculate_indicators(df_raw)
                if df_ind is not None:
                    last = df_ind.iloc[-1]
                    curr_p = last['c']
                    r, r9, r45 = last['rsi'], last['rsi9'], last['rsi45']
                    
                    if r > r9 and r > r45: r_stat = "TĂNG"
                    elif r < r9 and r < r45: r_stat = "GIẢM"
                    elif r > r45 and r < r9: r_stat = "CHỈNH (-)"
                    elif r < r45 and r > r9: r_stat = "HỒI (+)"
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
            status.update(label=f"Hoàn thành {asset['name']}", state="complete")
        
        if rows:
            display_df = pd.DataFrame(rows)
            st.table(display_df.style.applymap(color_df, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
        else:
            st.error(f"❌ Tài sản {asset['name']} hiện đang mất kết nối dữ liệu ở mọi nguồn.")

    time.sleep(60)
    st.rerun()

if __name__ == "__main__":
    main()
