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
exchange = ccxt.binance({'timeout': 20000, 'enableRateLimit': True})

def calculate_indicators(df):
    if df is None or len(df) < 30: return None
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
    """Hàm lấy dữ liệu từ Yahoo Finance ổn định cho máy chủ Web"""
    try:
        yf_map = {'1h':'1h','1d':'1d'}
        # Nếu hỏi khung giờ nhưng symbol là Index Việt Nam (thường ko có 1h), lấy 1d thay thế
        is_vn_index = symbol == "^VNINDEX"
        fetch_tf = '1d' if (is_vn_index and 'h' in tf) else (yf_map.get(tf, '1h' if 'h' in tf else '1d'))
        
        period = '730d' if fetch_tf == '1h' else 'max'
        df = yf.download(symbol, period=period, interval=fetch_tf, progress=False)
        
        if df.empty: return None
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={df.columns[0]:'ts','Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'})
        
        # Resample cho các khung không có sẵn
        if tf in ['4h','8h','12h','3d','1w','1M']:
            rule
