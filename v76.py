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
# 1. CẤU HÌNH (Thay TOKEN và ID của bạn)
# ==========================================
TOKEN = '8958414448:AAGIRkKyPtS9fmAUpZ6xAFJtvqUBpoZ63VE'
CHAT_ID = '6095817110'
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

LIST_ASSETS = [
    {"name": "BITCOIN", "symbol": "BTC-USD", "source": "yahoo"},
    {"name": "VÀNG", "symbol": "GC=F", "source": "yahoo"},
    {"name": "VN-INDEX", "symbol": "VNINDEX", "source": "vnstock"}
]

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1M', '3M']
WAIT_TIME = 60 

last_alerts = {}
last_terminal_state = {}

st.set_page_config(page_title="Master Trade Dashboard v122", layout="wide")
exchange = ccxt.binance({'timeout': 15000, 'enableRateLimit': True})

# ==========================================
# 2. BỘ NÃO TÍNH TOÁN (RSI RMA & MA CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 15: return None
    try:
        df = df.copy()
        if 'c' not in df.columns and 'Close' in df.columns:
            df['c'] = df['Close']
            
        df['ma10'] = df['c'].rolling(10, min_periods=1).mean()
        df['ma20'] = df['c'].rolling(20, min_periods=1).mean()
        df['ma50'] = df['c'].rolling(50, min_periods=1).mean()
        
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
# 3. TRUY XUẤT DỮ LIỆU ĐỘC LẬP (FIX LẶP SỐ)
# ==========================================
def resample_ohlc(df, rule):
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    logic = {'o':'first','h':'max','l':'min','c':'last','v':'sum'}
    return df.resample(rule).agg(logic).dropna().reset_index()

# QUAN TRỌNG: Key của cache phải chứa cả TF để không bị trùng số
@st.cache_data(ttl=30)
def fetch_data(name, symbol, source, tf):
    try:
        # A. VN-INDEX (Nguồn VCI ổn định nhất trên Cloud)
        if source == "vnstock":
            q = Quote(symbol=symbol, source='VCI')
            v_tf = '1H' if any(x in tf for x in ['m', 'h', 'H']) else '1D'
            df = q.history(start='2018-01-01', interval=v_tf)
            if df is None or df.empty: return None
            df = df.rename(columns={'time':'ts','open':'o','high':'h','low':'l','close':'c','volume':'v'})
        
        # B. BITCOIN & VÀNG (Yahoo)
        else:
            yf_tf = '1h' if any(x in tf for x in ['h', 'H', '2h', '4h', '8h', '12h']) else '1d'
            if '15m' in tf or '30m' in tf: yf_tf = tf
            
            period = '7d' if 'm' in tf else ('730d' if 'h' in yf_tf else 'max')
            df_raw = yf.download(symbol, period=period, interval=yf_tf, progress=False)
            if df_raw.empty: return None
            if isinstance(df_raw.columns, pd.MultiIndex): df_raw.columns = df_raw.columns.get_level_values(0)
            df = df_raw.reset_index().rename(columns={df_raw.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})

        # C. LOGIC GỘP NẾN
        rule_map = {'2h':'2H','4h':'4H','8h':'8H','12h':'12H','3d':'3D','1w':'W-MON','1M':'ME','3M':'3ME'}
        if tf in rule_map:
            df = resample_ohlc(df, rule_map[tf])
            
        return calculate_indicators(df)
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
    st.markdown("<h1 style='text-align: center; color: #00ffcc;'>🚀 Pro Master Dashboard v122</h1>", unsafe_allow_html=True)
    now_vn = datetime.now(VN_TZ).strftime('%H:%M:%S - %d/%m/%Y')
    st.write(f"<p style='text-align: center;'>Cập nhật: <b>{now_vn}</b></p>", unsafe_allow_html=True)

    for asset in LIST_ASSETS:
        with st.status(f"Đang đồng bộ {asset['name']}...", expanded=True) as status:
            data_rows = []
            sync_list = []
            asset_price = 0
            
            for tf in TIMEFRAMES:
                # Chặn khung giờ cho VN-INDEX nếu cần
                if asset['name'] == "VN-INDEX" and 'm' in tf: continue
                
                df = fetch_data(asset['name'], asset['symbol'], asset['source'], tf)
                if df is not None:
                    last = df.iloc[-1]
                    p = float(last['c'])
                    if asset_price == 0: asset_price = p
                    
                    r, r9, r45 = float(last['rsi']), float(last['rsi9']), float(last['rsi45'])
                    
                    if r > r9 and r > r45: r_stat, r_code = "TĂNG", 1
                    elif r < r9 and r < r45: r_stat, r_code = "GIẢM", -1
                    elif r9 > r > r45: r_stat, r_code = "CHỈNH (-)", 0
                    elif r45 > r > r9: r_stat, r_code = "HỒI (+)", 0
                    else: r_stat, r_code = "YẾU", 0
                    
                    # Xét đồng thuận gửi Telegram
                    agreement = "-"
                    if sync_list:
                        prev = sync_list[-1]
                        key = f"{asset['name']}_{prev['tf']}_{tf}"
                        if r_code == 1 and prev['code'] == 1:
                            agreement = "MUA (↑)"
                            if last_alerts.get(key) != "BUY":
                                try: bot.send_message(CHAT_ID, f"🚀 **ĐỒNG THUẬN MUA: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "BUY"
                        elif r_code == -1 and prev['code'] == -1:
                            agreement = "BÁN (↓)"
                            if last_alerts.get(key) != "SELL":
                                try: bot.send_message(CHAT_ID, f"🔻 **ĐỒNG THUẬN BÁN: {asset['name']}**\nKhung: `{prev['tf']}-{tf}`\nGiá: `{p:,.1f}`", parse_mode='Markdown')
                                except: pass
                                last_alerts[key] = "SELL"
                        else: last_alerts[key] = "NONE"

                    sync_list.append({"tf": tf, "code": r_code})
                    def sign(v1, v2): return "TĂNG" if v1 > v2 else "GIẢM"
                    
                    data_rows.append({
                        "Khung": tf.upper(),
                        "Sóng": sign(p, float(last['ma20'])),
                        "Đồng thuận": agreement,
                        "RSI 9/45": r_stat,
                        "P/MA50": sign(p, float(last['ma50'])),
                        "MA 10/20": sign(float(last['ma10']), float(last['ma20'])),
                        "RSI": int(r),
                        "Giá": f"{p:,.1f}"
                    })
            
            if data_rows:
                status.update(label=f"💠 {asset['name']} | Giá HT: {asset_price:,.1f}", state="complete")
                st.table(pd.DataFrame(data_rows).style.map(style_text, subset=['Sóng', 'RSI 9/45', 'P/MA50', 'MA 10/20']))
            else:
                status.update(label=f"❌ {asset['name']} lỗi dữ liệu.", state="error")

    time.sleep(WAIT_TIME)
    st.rerun()

if __name__ == "__main__":
    main()
