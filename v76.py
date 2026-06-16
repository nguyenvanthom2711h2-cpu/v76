import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import pytz

# Thử import vnstock
try:
    from vnstock import stock_historical_data
except ImportError:
    st.error("Cần thêm 'vnstock' vào file requirements.txt")

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH 
# ==========================================
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '8h', '12h', '1d', '3d', '1w', '1m', '3m']

st.set_page_config(page_title="Master Trade v152", layout="wide")

# ==========================================
# 2. THUẬT TOÁN KỸ THUẬT (CHUẨN)
# ==========================================
def calculate_indicators(df):
    if df is None or len(df) < 50: return None 
    try:
        df = df.copy()
        # Chuẩn hóa tên cột về chữ thường
        df.columns = [c.lower() for c in df.columns]
        col = 'close'
        
        # MA
        df['ma10'] = df[col].rolling(10).mean()
        df['ma20'] = df[col].rolling(20).mean()
        df['ma50'] = df[col].rolling(50).mean()
        
        # RSI Wilder's
        delta = df[col].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        
        df['rsi_val'] = 100 - (100 / (1 + avg_gain / avg_loss))
        df['rsi9'] = df['rsi_val'].rolling(9).mean()
        df['rsi45'] = df['rsi_val'].rolling(45).mean()
        return df
    except: return None

# ==========================================
# 3. TRUY XUẤT DỮ LIỆU TỪ NHIỀU NGUỒN
# ==========================================
def fetch_global_data(symbol, tf):
    """Lấy dữ liệu cho BTC và Vàng từ Yahoo Finance"""
    try:
        if tf in ['15m', '30m']: interval, period = tf, '60d'
        elif any(x in tf for x in ['h', '2h', '4h', '8h', '12h']): interval, period = '1h', '730d'
        else: interval, period = '1d', 'max'
        
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # Resampling
        rule_map = {'2h':'2h', '4h':'4h', '8h':'8h', '12h':'12h', '3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
        if tf in rule_map and tf != interval:
            df = df.resample(rule_map[tf]).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        
        return calculate_indicators(df)
    except: return None

def fetch_vn_data(tf):
    """Lấy dữ liệu cho VN-INDEX từ VNSTOCK (Nguồn SSI/TCBS)"""
    try:
        # Vnstock chỉ lấy được từ khung Ngày trở lên một cách ổn định trên Web
        if any(x in tf for x in ['m', 'h', 'H']): return None
        
        # Lấy dữ liệu Ngày từ Vnstock
        df = stock_historical_data(symbol='VNINDEX', 
                                   start_date='2015-01-01', 
                                   end_date=datetime.now().strftime('%Y-%m-%d'), 
                                   resolution='1D', type='index', source='SSI')
        
        if df is None or df.empty: return None
        
        # Resampling cho khung lớn
        rule_map = {'3d':'3D', '1w':'W-MON', '1m':'ME', '3m':'3ME'}
        if tf in rule_map:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
            df = df.resample(rule_map[tf]).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        
        return calculate_indicators(df)
    except: return None

# ==========================================
# 4. GIAO DIỆN HIỂN THỊ
# ==========================================
def style_text(val):
    if val in ["TĂNG", "HỒI (+)"]: return 'color: #00ff88; font-weight: bold;'
    if val in ["GIẢM", "CHỈNH (-)"]: return 'color: #ff4444; font-weight: bold;'
    return ''

def main():
    st.markdown("<h2 style='text-align: center; color: #00ffcc;'>🚀 Master Trade Dashboard v152</h2>", unsafe_allow_html=True)
    
    tabs = st.tabs(["BITCOIN", "VÀNG", "VN-INDEX"])

    # XỬ LÝ BITCOIN & VÀNG
    for i, asset in enumerate([{"n":"BITCOIN","s":"BTC-USD"}, {"n":"VÀNG","s":"GC=F"}]):
        with tabs[i]:
            data_rows = []
            with st.spinner(f"Đang tải {asset['n']} từ Yahoo..."):
                for tf in TIMEFRAMES:
                    df = fetch_global_data(asset['s'], tf)
                    if df is not None and not df.empty:
                        last = df.iloc[-1]
                        if pd.isna(last['rsi45']): continue
                        p_val = float(last['close'])
                        r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                        r_stat = "TĂNG" if r>r9 and r>r45 else ("GIẢM" if r<r9 and r<r45 else ("CHỈNH (-)" if r9>r>r45 else ("HỒI (+)" if r45>r>r9 else "YẾU")))
                        data_rows.append({"KHUNG": tf.upper(), "XU HƯỚNG": "TĂNG" if p_val > last['ma20'] else "GIẢM", "RSI 9/45": r_stat, "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", "MA 10/20": "TĂNG" if last['ma10']>last['ma20'] else "GIẢM", "RSI": int(r), "GIÁ": f"{p_val:,.1f}"})
            if data_rows: st.table(pd.DataFrame(data_rows).style.map(style_text))

    # XỬ LÝ VN-INDEX (NGUỒN RIÊNG)
    with tabs[2]:
        data_rows_vn = []
        with st.spinner("Đang tải VN-INDEX từ SSI..."):
            for tf in ['1d', '3d', '1w', '1m', '3m']:
                df = fetch_vn_data(tf)
                if df is not None and not df.empty:
                    last = df.iloc[-1]
                    p_val = float(last['close'])
                    r, r9, r45 = float(last['rsi_val']), float(last['rsi9']), float(last['rsi45'])
                    r_stat = "TĂNG" if r>r9 and r>r45 else ("GIẢM" if r<r9 and r<r45 else ("CHỈNH (-)" if r9>r>r45 else ("HỒI (+)" if r45>r>r9 else "YẾU")))
                    data_rows_vn.append({"KHUNG": tf.upper(), "XU HƯỚNG": "TĂNG" if p_val > last['ma20'] else "GIẢM", "RSI 9/45": r_stat, "P/MA50": "TĂNG" if p_val > last['ma50'] else "GIẢM", "MA 10/20": "TĂNG" if last['ma10']>last['ma20'] else "GIẢM", "RSI": int(r), "GIÁ": f"{p_val:,.2f}"})
        if data_rows_vn: st.table(pd.DataFrame(data_rows_vn).style.map(style_text))
        else: st.warning("VN-INDEX: Nguồn SSI/TCBS đang bị nghẽn IP. Hãy thử lại sau.")

    time.sleep(300)
    st.rerun()

if __name__ == "__main__":
    main()
