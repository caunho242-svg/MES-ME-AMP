import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import calendar
import hashlib
import secrets
import time
import re
import sqlite3
import json
import base64
import random
import string
import io
import os
import streamlit.components.v1 as components

try:
    from PIL import Image
except ImportError:
    pass

# ==========================================
# CẤU HÌNH TRANG & LOGO GỐC CỦA STREAMLIT
# ==========================================
try:
    if os.path.exists("ME-AMP.jpg"):
        app_icon = Image.open("ME-AMP.jpg")
    else:
        app_icon = "⚙️"
except Exception:
    app_icon = "⚙️"

st.set_page_config(
    page_title="ME-AMP | Factory Management",
    page_icon=app_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CẤU HÌNH TRẢI NGHIỆM APP DI ĐỘNG (PWA + MANIFEST TỰ ĐỘNG)
# ==========================================
def get_logo_base64(file_path="ME-AMP.jpg"):
    """Đọc file logo nội bộ và chuyển sang base64. Nếu không có file thì dùng logo mặc định."""
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        ext = file_path.split('.')[-1].lower()
        mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
        return f"data:{mime_type};base64,{encoded}"
    return "https://cdn-icons-png.flaticon.com/512/3652/3652191.png"

APP_LOGO_URL = get_logo_base64("ME-AMP.jpg")

# Tạo cấu trúc file manifest.json (ảo) ép trình duyệt di động nhận diện App
manifest_json = f"""{{
    "name": "ME-AMP Factory",
    "short_name": "ME-AMP",
    "start_url": ".",
    "display": "standalone",
    "background_color": "#0a192f",
    "theme_color": "#facc15",
    "icons": [
        {{
            "src": "{APP_LOGO_URL}",
            "sizes": "192x192",
            "type": "image/jpeg"
        }},
        {{
            "src": "{APP_LOGO_URL}",
            "sizes": "512x512",
            "type": "image/jpeg"
        }}
    ]
}}"""
manifest_b64 = base64.b64encode(manifest_json.encode('utf-8')).decode()
manifest_url = f"data:application/manifest+json;base64,{manifest_b64}"

# JS ép xóa thẻ icon cũ của Streamlit và chèn thẻ icon mới + manifest
components.html(f"""
<script>
    const head = window.parent.document.querySelector("head");
    
    // Xóa triệt để các logo mặc định mà Streamlit tự sinh ra
    const existingIcons = window.parent.document.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]');
    existingIcons.forEach(icon => icon.remove());

    if (!window.parent.document.getElementById("pwa-meta")) {{
        const metaTags = `
            <meta id="pwa-meta" name="apple-mobile-web-app-capable" content="yes">
            <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
            <meta name="theme-color" content="#0a192f">
            <meta name="mobile-web-app-capable" content="yes">
            <link rel="icon" type="image/jpeg" href="{APP_LOGO_URL}">
            <link rel="apple-touch-icon" href="{APP_LOGO_URL}">
            <link rel="manifest" href="{manifest_url}">
        `;
        head.insertAdjacentHTML("beforeend", metaTags);
    }}
</script>
""", height=0, width=0)

ALL_FEATURES = [
    "🎛️ Dashboard OEE",
    "📦 Kho Spare Part",
    "🏭 Quản Lý Máy Móc",
    "👤 Quản Lý Tài Khoản"
]

ALL_MACHINE_EDIT_FIELDS = [
    "Tên máy",
    "Dây chuyền (Line)",
    "Đường dẫn máy",
    "File mẫu dữ liệu"
]

SESSION_TIMEOUT = 1800 
MAX_LOGIN_ATTEMPTS = 5 
LOCKOUT_DURATION = 300 

# ==========================================
# 🗄️ KẾT NỐI CƠ SỞ DỮ LIỆU SQLITE
# ==========================================
def get_db_connection():
    conn = sqlite3.connect('mes_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# CÁC HÀM BẢO MẬT & TIỆN ÍCH
# ==========================================
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + ":" + key.hex()

def verify_password(password, hashed_pass):
    try:
        salt, _ = hashed_pass.split(':')
        return hash_password(password, salt) == hashed_pass
    except Exception:
        return False

def validate_username(username):
    return bool(re.match(r"^[a-zA-Z0-9_]{3,20}$", username))

def validate_password_strength(password):
    if len(password) < 8: return False, "Mật khẩu phải có ít nhất 8 ký tự!"
    if not re.search(r"[A-Z]", password): return False, "Phải chứa ít nhất 1 chữ hoa!"
    if not re.search(r"[a-z]", password): return False, "Phải chứa ít nhất 1 chữ thường!"
    if not re.search(r"\d", password): return False, "Phải chứa ít nhất 1 chữ số!"
    if not re.search(r"[@$!%*?&#]", password): return False, "Phải chứa ít nhất 1 ký tự đặc biệt (@, $, !, %, *, ?, &, #)!"
    return True, "Hợp lệ"

def generate_strong_password():
    chars = string.ascii_letters + string.digits + "@$!%*?&#"
    p = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("@$!%*?&#")
    ]
    p += [random.choice(chars) for _ in range(6)]
    random.shuffle(p)
    return "".join(p)

def log_security_event(username, event_type, status):
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    username TEXT,
                    event_type TEXT,
                    status TEXT
                )''')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO audit_logs (timestamp, username, event_type, status) VALUES (?,?,?,?)", (timestamp, username, event_type, status))
    conn.commit()
    conn.close()

def image_to_base64(uploaded_file):
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        encoded = base64.b64encode(bytes_data).decode()
        file_extension = uploaded_file.name.split('.')[-1].lower()
        if file_extension == 'jpg': file_extension = 'jpeg'
        return f"data:image/{file_extension};base64,{encoded}"
    return None

def compare_images_mse(img1_bytes, b64_str2):
    try:
        i1 = Image.open(io.BytesIO(img1_bytes)).convert('L').resize((32, 32))
        _, encoded = b64_str2.split(",", 1)
        i2 = Image.open(io.BytesIO(base64.b64decode(encoded))).convert('L').resize((32, 32))
        arr1 = np.array(i1, dtype=float)
        arr2 = np.array(i2, dtype=float)
        mse = np.mean((arr1 - arr2) ** 2)
        return mse
    except Exception:
        return float('inf')

def generate_printable_html(df, title):
    html = f"""
    <html>
    <head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Inter', 'Arial', sans-serif; padding: 20px; color: #000000; }}
        h2 {{ text-align: center; color: #1e3a8a; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 14px; border: 1px solid #cbd5e1; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; color: #000000; }}
        th {{ background-color: #f1f5f9; color: #000000; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f8fafc; }}
    </style>
    </head>
    <body onload="window.print()">
    <h2>{title} ({date.today().strftime('%d/%m/%Y')})</h2>
    {df.to_html(index=False)}
    <p style="text-align: right; margin-top: 20px; font-style: italic; font-weight: bold; color: #000000;">Phần mềm quản lý ME-AMP</p>
    </body>
    </html>
    """
    return base64.b64encode(html.encode('utf-8-sig')).decode()

def generate_mock_machine_data(machine_obj, start_date, end_date):
    date_range = pd.date_range(start=start_date, end=end_date)
    data = []
    seed_val = sum(ord(c) for c in machine_obj["id"]) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    for d in date_range:
        availability = np.random.uniform(80, 98)
        performance = np.random.uniform(85, 99)
        quality = np.random.uniform(95, 99.9)
        oee = (availability * performance * quality) / 10000
        downtime = round(np.random.uniform(10, 120), 1)
        data.append({
            "Ngày": d.strftime("%Y-%m-%d"), "Mã máy": machine_obj["id"], "Tên máy": machine_obj["name"],
            "Dây chuyền": machine_obj["line"], "Sẵn sàng (%)": round(availability, 1),
            "Hiệu suất (%)": round(performance, 1), "Chất lượng (%)": round(quality, 1),
            "OEE (%)": round(oee, 1), "Downtime (Phút)": downtime
        })
    return pd.DataFrame(data)

def generate_mock_pareto_4m_data(machine_ids, start_date, end_date):
    seed_val = sum(ord(c) for m in machine_ids for c in m) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    stations = ["Block 1", "Block 2", "Block 3", "Block 4", "Block 5", "Block 6", "Chưa xác định"]
    downtimes = np.random.randint(200, 3000, size=len(stations))
    df_pareto = pd.DataFrame({"Trạm": stations, "So_Phut": downtimes})
    df_pareto = df_pareto.sort_values(by="So_Phut", ascending=False).reset_index(drop=True)
    tong_thoi_gian = df_pareto["So_Phut"].sum()
    df_pareto["Phan_Tram_Tich_Luy"] = (df_pareto["So_Phut"].cumsum() / tong_thoi_gian) * 100
    
    m_machine = int(np.random.uniform(500, 2000))
    m_material = int(np.random.uniform(300, 1500))
    m_method = int(np.random.uniform(100, 800))
    m_unclassified = int(np.random.uniform(100, 600))
    
    data_4m = {
        "labels": ['Máy móc (Machine)', 'Nguyên liệu (Material)', 'Phương pháp (Method)', 'Chưa phân loại'],
        "values": [m_machine, m_material, m_method, m_unclassified]
    }
    return df_pareto, data_4m

# ==========================================
# KHỞI TẠO BẢNG & DỮ LIỆU
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, 
                    password_hash TEXT, 
                    name TEXT, 
                    department TEXT, 
                    position TEXT, 
                    role TEXT, 
                    allowed_pages TEXT, 
                    machine_perms TEXT, 
                    editable_machine_fields TEXT, 
                    spare_perms TEXT, 
                    last_active REAL DEFAULT 0
                )''')
    try: 
        c.execute("ALTER TABLE users ADD COLUMN spare_perms TEXT")
    except sqlite3.OperationalError: 
        pass
    try: 
        c.execute("ALTER TABLE users ADD COLUMN last_active REAL DEFAULT 0")
    except sqlite3.OperationalError: 
        pass
        
    c.execute('''CREATE TABLE IF NOT EXISTS machines (id TEXT PRIMARY KEY, name TEXT, line TEXT, url TEXT, template_file TEXT, has_file INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS spare_parts (part_id TEXT PRIMARY KEY, part_name TEXT, category TEXT, model_applicable TEXT, location TEXT, quantity INTEGER, min_quantity INTEGER, unit TEXT, image_url TEXT)''')
    try: 
        c.execute("ALTER TABLE spare_parts ADD COLUMN image_url TEXT")
    except sqlite3.OperationalError: 
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS spare_part_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, part_id TEXT, action_type TEXT, quantity_changed INTEGER, remaining_qty INTEGER, user_action TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS spare_request_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, part_id TEXT, part_name TEXT, quantity_requested INTEGER, requester TEXT, line_working TEXT, notes TEXT, status TEXT)''')
    try: 
        c.execute("ALTER TABLE spare_request_queue ADD COLUMN line_working TEXT")
    except sqlite3.OperationalError: 
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, username TEXT, event_type TEXT, status TEXT)''')

    default_spare_perms = json.dumps(["Xem", "Giao dịch", "Thêm mới", "Chỉnh sửa", "Phê duyệt"])
    c.execute("SELECT username FROM users WHERE username='admin'")
    if not c.fetchone():
        admin_pass = hash_password("Admin@123")
        c.execute('''INSERT INTO users (username, password_hash, name, department, position, role, allowed_pages, machine_perms, editable_machine_fields, spare_perms, last_active) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                  ('admin', admin_pass, 'Giám Đốc Nhà Máy', 'Ban Giám Đốc', 'Giám Đốc', 'Admin', json.dumps(ALL_FEATURES), json.dumps(["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"]), json.dumps(ALL_MACHINE_EDIT_FIELDS), default_spare_perms, 0))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# ĐỌC ẢNH NỀN "pexels-edward-jenner-4253268.jpg"
# ==========================================
@st.cache_data
def get_background_base64(file_path):
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

bg_img = get_background_base64("pexels-edward-jenner-4253268.jpg")

if bg_img:
    bg_style = f"""
    background-image: 
        repeating-linear-gradient(45deg, rgba(0, 0, 0, 0.08) 0px, rgba(0, 0, 0, 0.08) 2px, transparent 2px, transparent 6px),
        url("data:image/jpeg;base64,{bg_img}");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    """
else:
    bg_style = """
    background-image: 
        repeating-linear-gradient(45deg, rgba(0, 0, 0, 0.08) 0px, rgba(0, 0, 0, 0.08) 2px, transparent 2px, transparent 6px),
        linear-gradient(135deg, #008eb0 40%, #e08963 60%);
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    """

# ==========================================
# CSS GIAO DIỆN CHÍNH
# ==========================================
st.markdown(f"""
    <style>
    .stApp {{
        {bg_style}
    }}
    </style>
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&family=Orbitron:wght@500;700;900&display=swap');
    
    .stApp { color: #ffffff; font-family: 'Inter', sans-serif; }
    .stMarkdown p, .stMarkdown span { color: #ffffff !important; font-weight: 600 !important; }
    label { color: #ffffff !important; font-weight: 600 !important; text-shadow: none !important; }
    
    h1, h2, h3, h4 { 
        color: #facc15 !important; 
        text-shadow: 0px 2px 8px rgba(0,0,0,0.8), 0 0 10px rgba(250, 204, 21, 0.6) !important; 
        font-family: 'Orbitron', sans-serif; 
        letter-spacing: 0.5px; 
        font-weight: 900 !important;
    }
    
    div[data-testid="stToast"] { background: rgba(10, 25, 47, 0.95) !important; border: 2px solid #facc15 !important; box-shadow: 0 8px 30px rgba(250, 204, 21, 0.4) !important; border-radius: 10px !important; z-index: 99999 !important; }
    div[data-testid="stToast"] * { color: #ffffff !important; font-family: 'Inter', sans-serif !important; font-weight: 700 !important; text-shadow: none !important;}
    .stAlert { background: rgba(10, 25, 47, 0.9) !important; font-weight: 600; border-left: 5px solid #facc15; box-shadow: 0 4px 15px rgba(0,0,0,0.6); color: #ffffff !important; }
    
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div, textarea { 
        background-color: #ffffff !important; color: #000000 !important; border: 2px solid #facc15 !important; border-radius: 8px; font-family: 'Inter', sans-serif; font-weight: 800 !important; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1); text-shadow: none !important;
    }
    .stTextInput>div>div>input::placeholder, .stNumberInput>div>div>input::placeholder, textarea::placeholder { color: #64748b !important; font-weight: 500; opacity: 1; }
    .stTextInput>div>div>input:focus, .stSelectbox>div>div>div:focus, textarea:focus { border-color: #3b82f6 !important; box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.5) !important; outline: none; }
    
    div[data-baseweb="popover"] ul * { color: #000000 !important; font-weight: 700 !important; text-shadow: none !important; }
    div[data-baseweb="popover"] ul { background-color: #ffffff !important; border: 2px solid #facc15 !important; }
    div[data-testid="stDataFrame"] * { text-shadow: none !important; }

    .stApp button[kind="primary"], .stApp button[kind="secondary"], .stApp button[kind="secondaryFormSubmit"], .stApp button[kind="primaryFormSubmit"], .stApp div[data-testid="stPopover"] button, .stApp div[data-testid="stCameraInput"] button, .stApp div[data-testid="stFileUploader"] button, .stApp div[data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%) !important; background-color: #facc15 !important; border: none !important; border-radius: 8px !important; box-shadow: 0 4px 10px rgba(0,0,0,0.5), 0 0 15px rgba(250, 204, 21, 0.4) !important; transition: all 0.2s ease !important;
    }

    .stApp button[kind="primary"] span, .stApp button[kind="secondary"] span, .stApp button[kind="secondaryFormSubmit"] span, .stApp button[kind="primaryFormSubmit"] span, .stApp div[data-testid="stPopover"] button span, .stApp div[data-testid="stPopover"] button div, .stApp div[data-testid="stCameraInput"] button span, .stApp div[data-testid="stFileUploader"] button span, .stApp div[data-testid="stDownloadButton"] button span {
        color: #000000 !important; text-shadow: none !important;
    }

    .stApp button[kind="primary"] p, .stApp button[kind="secondary"] p, .stApp button[kind="secondaryFormSubmit"] p, .stApp button[kind="primaryFormSubmit"] p, .stApp div[data-testid="stPopover"] button p, .stApp div[data-testid="stCameraInput"] button p, .stApp div[data-testid="stFileUploader"] button p, .stApp div[data-testid="stDownloadButton"] button p {
        color: #000000 !important; font-weight: 900 !important; font-family: 'Inter', sans-serif !important; text-shadow: none !important; margin: 0 !important;
    }

    .stApp span.material-symbols-rounded, .stApp button span.material-symbols-rounded, .stApp div[data-testid="stPopover"] button span.material-symbols-rounded {
        font-family: 'Material Symbols Rounded' !important; font-weight: normal !important; font-style: normal !important; font-size: 24px !important; color: #000000 !important;
    }

    .stApp button[kind="primary"]:hover, .stApp button[kind="secondary"]:hover, .stApp button[kind="secondaryFormSubmit"]:hover, .stApp button[kind="primaryFormSubmit"]:hover, .stApp div[data-testid="stPopover"] button:hover, .stApp div[data-testid="stCameraInput"] button:hover, .stApp div[data-testid="stFileUploader"] button:hover, .stApp div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-2px) !important; box-shadow: 0 6px 15px rgba(0,0,0,0.6), 0 0 25px rgba(250, 204, 21, 0.7) !important; background: linear-gradient(135deg, #fef08a 0%, #eab308 100%) !important; background-color: #fef08a !important;
    }

    div[data-testid="stPopoverBody"] { background-color: #0a192f !important; background-image: linear-gradient(rgba(250, 204, 21, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(250, 204, 21, 0.05) 1px, transparent 1px) !important; background-size: 20px 20px !important; border: 2px solid #facc15 !important; border-radius: 12px !important; box-shadow: 0 8px 30px rgba(0,0,0,0.8) !important; }
    div[data-testid="stPopoverBody"] label, div[data-testid="stPopoverBody"] p, div[data-testid="stPopoverBody"] span, div[data-testid="stPopoverBody"] div { color: #ffffff !important; text-shadow: none !important; }
    div[data-testid="stPopoverBody"] strong, div[data-testid="stPopoverBody"] h1, div[data-testid="stPopoverBody"] h2, div[data-testid="stPopoverBody"] h3 { color: #facc15 !important; }
    div[data-testid="stPopoverBody"] input { background-color: #ffffff !important; color: #000000 !important; }

    div[data-testid="stFileUploaderDropzone"] { background-color: #ffffff !important; border: 2px dashed #facc15 !important; border-radius: 8px !important; }
    div[data-testid="stFileUploaderDropzone"] * { color: #000000 !important; font-weight: 800 !important; text-shadow: none !important; }
    
    div.stRadio > div[role="radiogroup"] > label { background-color: rgba(10, 25, 47, 0.8) !important; border: 1px solid #334155 !important; border-radius: 8px !important; margin-bottom: 8px !important; padding: 10px 15px !important; transition: all 0.2s ease !important; box-shadow: 0 2px 4px rgba(0,0,0,0.4) !important; }
    div.stRadio > div[role="radiogroup"] > label p, div.stRadio > div[role="radiogroup"] > label span, div.stRadio > div[role="radiogroup"] > label div { color: #ffffff !important; font-weight: 700 !important; text-shadow: none !important; }
    div.stRadio > div[role="radiogroup"] > label:hover { border-color: #facc15 !important; background-color: #0f172a !important; transform: translateX(4px) !important; box-shadow: 0 0 10px rgba(250,204,21,0.5) !important; }
    div.stRadio > div[role="radiogroup"] > label[data-checked="true"] { border-color: #facc15 !important; background-color: #0f172a !important; border-left: 5px solid #facc15 !important; }
    div.stRadio > div[role="radiogroup"] > label[data-checked="true"] p, div.stRadio > div[role="radiogroup"] > label[data-checked="true"] span, div.stRadio > div[role="radiogroup"] > label[data-checked="true"] div { color: #facc15 !important; font-weight: 800 !important; }

    .login-header-card, div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlockBorderWrapper"] { background: rgba(10, 25, 47, 0.92) !important; border: 1px solid #facc15 !important; border-radius: 12px !important; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.7) !important; backdrop-filter: blur(10px); }
    
    .kpi-card-1, .kpi-card-2, .kpi-card-3, .kpi-card-4 { background: rgba(10, 25, 47, 0.9); padding: 18px; border-radius: 10px; border: 1px solid #facc15; box-shadow: 0 4px 10px rgba(0,0,0,0.6); color: #ffffff !important; transition: transform 0.2s; }
    .kpi-card-1:hover, .kpi-card-2:hover, .kpi-card-3:hover, .kpi-card-4:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(250, 204, 21, 0.5); }
    .kpi-card-1 h2, .kpi-card-2 h2, .kpi-card-3 h2, .kpi-card-4 h2 { color: #facc15 !important; text-shadow: 0 0 12px rgba(250, 204, 21, 0.6) !important; font-weight: 900; }

    .online-bar { background: linear-gradient(90deg, #1e3a8a 0%, #0f172a 100%); padding: 12px 18px; border-radius: 10px; border: 2px solid #facc15; margin-bottom: 20px; color: #ffffff !important; font-family: 'Inter', sans-serif; font-weight: 800; box-shadow: 0 4px 20px rgba(250, 204, 21, 0.3); display: flex; align-items: center; gap: 10px; z-index: 100; position: relative; }
    .online-bar b { color: #facc15 !important; text-shadow: 1px 1px 2px #000; }
    .streamlit-expanderHeader { font-weight: 800 !important; color: #facc15 !important; text-shadow: 1px 1px 3px rgba(0,0,0,0.8); }
    
    @media print {
        [data-testid="stSidebar"], button, .online-bar, div.stRadio, header { display: none !important; }
        .stApp { background: white !important; color: black !important; background-image: none !important; }
        * { text-shadow: none !important; box-shadow: none !important; color: black !important; border-color: black !important; }
    }
    </style>
""", unsafe_allow_html=True)

@st.dialog("🔔 THÔNG BÁO HỆ THỐNG")
def show_popup_message(title, message, icon="ℹ️"):
    st.markdown(f"### {icon} {title}")
    st.write(message)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

# Authentication
if "LOGIN_ATTEMPTS" not in st.session_state: st.session_state["LOGIN_ATTEMPTS"] = {}
if "selected_menu" not in st.session_state: st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

def login():
    _, col_center, _ = st.columns([1, 2.2, 1])
    with col_center:
        st.markdown("""
            <div class="login-header-card" style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;">
                <div style="font-size: 5rem; margin-bottom: 5px; text-shadow: 0 4px 15px rgba(250, 204, 21, 0.4);">⚙️🛠️</div>
                <div style="color: #facc15; font-size: 3.5rem; font-weight: 900; margin-bottom: 5px; letter-spacing: 2px; font-family: 'Orbitron', sans-serif; text-shadow: 0 0 10px rgba(250,204,21,0.6);">ME-AMP</div>
                <div style="color: #ffffff; font-size: 1.2rem; font-weight: 800; font-family: 'Inter', sans-serif; text-transform: uppercase;">Hệ Thống Quản Lý</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 ĐĂNG NHẬP")
            with st.form("login_form"):
                username = st.text_input("👤 Tên đăng nhập", placeholder="Nhập tên đăng nhập")
                password = st.text_input("🔑 Mật khẩu", type="password", placeholder="Nhập mật khẩu")
                submit_button = st.form_submit_button("🚀 KHỞI ĐỘNG HỆ THỐNG", use_container_width=True, type="primary")
                
                if submit_button:
                    username_cleaned = username.strip().lower()
                    attempts_info = st.session_state["LOGIN_ATTEMPTS"].get(username_cleaned, {"count": 0, "lockout_until": 0})
                    if time.time() < attempts_info["lockout_until"]:
                        st.error(f"❌ Tài khoản đang bị khóa. Thử lại sau {int(attempts_info['lockout_until'] - time.time())} giây!")
                    else:
                        conn = get_db_connection()
                        user = conn.execute("SELECT * FROM users WHERE username = ?", (username_cleaned,)).fetchone()
                        conn.close()

                        if user and verify_password(password, user['password_hash']):
                            st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = {"count": 0, "lockout_until": 0}
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = username_cleaned
                            st.session_state["user_info"] = {
                                "name": user['name'], "department": user['department'], "position": user['position'],
                                "role": user['role'], "allowed_pages": json.loads(user['allowed_pages']),
                                "machine_perms": json.loads(user['machine_perms']), "editable_machine_fields": json.loads(user['editable_machine_fields']) if user['editable_machine_fields'] else [],
                                "spare_perms": json.loads(user['spare_perms']) if user['spare_perms'] else ["Xem", "Giao dịch"]
                            }
                            st.session_state["last_activity"] = time.time() 
                            st.rerun()
                        else:
                            if user:
                                attempts_info["count"] += 1
                                if attempts_info["count"] >= MAX_LOGIN_ATTEMPTS:
                                    attempts_info["lockout_until"] = time.time() + LOCKOUT_DURATION
                                    st.error("❌ Bị khóa 5 phút do nhập sai quá nhiều!")
                                else:
                                    st.error(f"❌ Sai mật khẩu! (Còn {MAX_LOGIN_ATTEMPTS - attempts_info['count']} lần)")
                            else:
                                st.error("❌ Tài khoản không tồn tại!")
                            st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = attempts_info
        st.markdown("<p style='text-align: center; color: #ffffff; font-size: 0.9rem; margin-top: 30px; font-weight: 700; text-shadow: 1px 1px 2px #000;'>© 2026 ME-AMP Core System | AI-Powered Enterprise</p>", unsafe_allow_html=True)

def logout():
    if "username" in st.session_state:
        conn = get_db_connection()
        conn.execute("UPDATE users SET last_active = 0 WHERE username = ?", (st.session_state["username"],))
        conn.commit()
        conn.close()
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user_info", None)
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    if (time.time() - st.session_state.get("last_activity", 0)) > SESSION_TIMEOUT:
        logout()
        st.rerun()
    else:
        st.session_state["last_activity"] = time.time() 

    current_user = st.session_state["user_info"]
    current_username = st.session_state.get("username", "admin")
    
    conn = get_db_connection()
    conn.execute("UPDATE users SET last_active = ? WHERE username = ?", (time.time(), current_username))
    conn.commit()
    conn.close()

    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #facc15; text-shadow: 0 0 15px rgba(250,204,21,0.6); font-size: 2.8rem;'>ME-AMP</h2>", unsafe_allow_html=True)
        st.success(f"👋 **{current_user['name']}**")
        st.info(f"📍 Bộ phận: **{current_user.get('department', 'N/A')}**\n\n💼 Chức vụ: **{current_user.get('position', 'N/A')}**\n\n🔑 Quyền: **{current_user.get('role', 'N/A')}**")
        
        with st.popover("🔑 Đổi mật khẩu cá nhân", use_container_width=True):
            with st.form("personal_pwd_form"):
                st.markdown("**Đổi mật khẩu tài khoản của bạn**")
                old_p = st.text_input("Mật khẩu hiện tại*", type="password")
                new_p = st.text_input("Mật khẩu mới*", type="password")
                cfm_p = st.text_input("Xác nhận mật khẩu mới*", type="password")
                
                if st.form_submit_button("💾 Cập nhật", type="primary", use_container_width=True):
                    if not old_p or not new_p or not cfm_p:
                        st.error("Vui lòng nhập đầy đủ thông tin!")
                    elif new_p != cfm_p:
                        st.error("Mật khẩu mới và xác nhận không khớp!")
                    else:
                        conn = get_db_connection()
                        db_user = conn.execute("SELECT password_hash FROM users WHERE username = ?", (current_username,)).fetchone()
                        if not verify_password(old_p, db_user["password_hash"]):
                            st.error("Mật khẩu hiện tại không đúng!")
                        else:
                            is_valid, msg = validate_password_strength(new_p)
                            if not is_valid:
                                st.error(msg)
                            else:
                                conn.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new_p), current_username))
                                conn.commit()
                                log_security_event(current_username, "ĐỔI MẬT KHẨU CÁ NHÂN", "Thành công")
                                st.success("✅ Đổi mật khẩu thành công!")
                        conn.close()

        st.markdown("---")
        
        user_pages = current_user.get("allowed_pages", ["🎛️ Dashboard OEE"])
        if "🎛️ Dashboard OEE" in user_pages:
            user_pages.remove("🎛️ Dashboard OEE")
            user_pages.insert(0, "🎛️ Dashboard OEE")

        if st.session_state["selected_menu"] not in user_pages:
            st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

        selected_menu = st.radio("📌 ĐIỀU HƯỚNG HỆ THỐNG", user_pages, key="menu_radio")
        if selected_menu != st.session_state["selected_menu"]:
            st.session_state["selected_menu"] = selected_menu
            st.rerun()

        st.markdown("---")
        st.button("🚪 Đăng xuất an toàn", on_click=logout, use_container_width=True)

    # =========================================================================
    # THANH HIỂN THỊ NGƯỜI DÙNG ONLINE TOÀN CỤC
    # =========================================================================
    conn = get_db_connection()
    online_users_db = conn.execute("SELECT name, department FROM users WHERE last_active >= ?", (time.time() - 300,)).fetchall()
    machine_db_raw = conn.execute("SELECT * FROM machines").fetchall()
    machine_db = [{"id": m["id"], "name": m["name"], "line": m["line"], "url": m["url"], "template_file": m["template_file"], "has_file": bool(m["has_file"])} for m in machine_db_raw]
    conn.close()
    
    if online_users_db:
        online_names = [f"🟢 <b>{u['name']}</b> ({u['department']})" for u in online_users_db]
        st.markdown(f"""
            <div class='online-bar'>
                <span style="font-size: 24px;">👥</span> 
                <span><b>Hệ thống ME-AMP đang trực tuyến ({len(online_users_db)}):</b> {' &nbsp;&nbsp;|&nbsp;&nbsp; '.join(online_names)}</span>
            </div>
        """, unsafe_allow_html=True)

    # =========================================================================
    # TRANG 1: DASHBOARD OEE
    # =========================================================================
    if selected_menu == "🎛️ Dashboard OEE":
        st.markdown("""<div style="background: rgba(10, 25, 47, 0.9); padding: 22px; border-radius: 12px; text-align: center; border: 1px solid #facc15; margin-bottom: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.5);">
                        <h1 style="margin: 0; font-size: 2.4rem; font-weight: 900; letter-spacing: 2px;">🎛️ QUẢN TRỊ HIỆU SUẤT TỔNG THỂ (OEE)</h1>
                    </div>""", unsafe_allow_html=True)

        st.subheader("🔍 Bộ Lọc Phân Tích")
        existing_lines = sorted(list(set([m["line"] for m in machine_db if m.get("line")])))
        line_options = ["Tất cả Lines"] + existing_lines
        machine_options = ["Tất cả Máy"] + [f"{m['id']} - {m['name']} (Line: {m['line']})" for m in machine_db]

        filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([2.5, 2.5, 2.5, 2.5, 2])
        with filter_col1: start_date = st.date_input("Từ ngày", date(2026, 8, 1))
        with filter_col2: end_date = st.date_input("Đến ngày", date.today())
        with filter_col3: selected_line = st.selectbox("Dây Chuyền (Line)", line_options)
        with filter_col4: selected_machine_str = st.selectbox("Mã / Tên Thiết Bị", machine_options)
        with filter_col5:
            st.write("")
            st.write("")
            btn_search = st.button("🔎 Phân tích", use_container_width=True, type="primary")

        filtered_machines = machine_db.copy()
        if selected_line != "Tất cả Lines": filtered_machines = [m for m in filtered_machines if m["line"] == selected_line]
        if selected_machine_str != "Tất cả Máy": filtered_machines = [m for m in filtered_machines if m["id"] == selected_machine_str.split(" - ")[0]]
        target_display_name = selected_machine_str if selected_machine_str != "Tất cả Máy" else (selected_line if selected_line != "Tất cả Lines" else "Toàn Nhà Máy")

        if btn_search: show_popup_message("CẬP NHẬT", f"Đã quét dữ liệu cho: **{target_display_name}**!", icon="📊")
        st.markdown("---")

        all_df_list = [generate_mock_machine_data(m, start_date, end_date) for m in filtered_machines]
        if all_df_list:
            df_filtered = pd.concat(all_df_list, ignore_index=True)
            avg_avail = df_filtered["Sẵn sàng (%)"].mean()
            
            st.markdown(f"### ⚙️ Chỉ Số Sức Khỏe Thiết Bị <span style='font-size: 1rem; color: #facc15;'>( {target_display_name} )</span>", unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            with k1: st.markdown(f'''<div class="kpi-card-1"><span style="font-size: 15px; font-weight: 800;">Downtime Rate</span><h2 style="margin: 5px 0 0 0;">{round(100 - avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k2: st.markdown(f'''<div class="kpi-card-2"><span style="font-size: 15px; font-weight: 800;">Availability</span><h2 style="margin: 5px 0 0 0;">{round(avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k3: st.markdown(f'''<div class="kpi-card-3"><span style="font-size: 15px; font-weight: 800;">MTBF</span><h2 style="margin: 5px 0 0 0;">{int(df_filtered["Downtime (Phút)"].mean() * 2)} Phút</h2></div>''', unsafe_allow_html=True)
            with k4: st.markdown(f'''<div class="kpi-card-4"><span style="font-size: 15px; font-weight: 800;">MTTR</span><h2 style="margin: 5px 0 0 0;">{round(df_filtered["Downtime (Phút)"].sum() / max(len(df_filtered), 1), 1)} Phút</h2></div>''', unsafe_allow_html=True)

            st.markdown("---")
            if str(current_user.get("role", "")).lower() in ["manager", "admin"]:
                st.markdown(f"### 📊 Phân Tích Pareto (80/20)")
                df_pareto, data_4m = generate_mock_pareto_4m_data([m["id"] for m in filtered_machines], start_date, end_date)
                p_col, pie_col = st.columns([6, 4])
                with p_col:
                    with st.container(border=True):
                        fig_p = make_subplots(specs=[[{"secondary_y": True}]])
                        fig_p.add_trace(go.Bar(x=df_pareto["Trạm"], y=df_pareto["So_Phut"], name="Downtime", marker_color="#facc15"), secondary_y=False)
                        fig_p.add_trace(go.Scatter(x=df_pareto["Trạm"], y=df_pareto["Phan_Tram_Tich_Luy"], name="% Luỹ kế", mode="lines+markers+text", text=df_pareto["Phan_Tram_Tich_Luy"].round(0).astype(str)+"%", textposition="top left", marker=dict(color="#60a5fa")), secondary_y=True)
                        fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                        st.plotly_chart(fig_p, use_container_width=True)
                with pie_col:
                    with st.container(border=True):
                        fig_pie = go.Figure(data=[go.Pie(labels=data_4m["labels"], values=data_4m["values"], hole=.4, marker=dict(colors=['#facc15', '#eab308', '#ca8a04', '#a16207']))])
                        fig_pie.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.1), paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                        st.plotly_chart(fig_pie, use_container_width=True)

            st.markdown("---")
            st.markdown("### 📈 Xu Hướng Chỉ Số OEE")
            c_chart, c_tbl = st.columns([6, 4])
            with c_chart:
                with st.container(border=True):
                    fig_l = go.Figure()
                    for m_item in filtered_machines:
                        d_sub = df_filtered[df_filtered["Mã máy"] == m_item["id"]]
                        fig_l.add_trace(go.Scatter(x=d_sub["Ngày"], y=d_sub["OEE (%)"], mode='lines+markers', name=m_item['name']))
                    fig_l.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_l, use_container_width=True)
            with c_tbl:
                with st.expander("🖱️ Bảng Dữ Liệu Chi Tiết", expanded=True):
                    st.dataframe(df_filtered[["Ngày", "Mã máy", "Tên máy", "OEE (%)", "Downtime (Phút)"]], use_container_width=True, height=320)

    # =========================================================================
    # TRANG 2: KHO SPARE PART
    # =========================================================================
    elif selected_menu == "📦 Kho Spare Part":
        st.markdown("## 📦 QUẢN LÝ KHO PHỤ TÙNG & VẬT TƯ (SPARE PARTS)")
        st.markdown("---")

        user_spare_perms = current_user.get("spare_perms", ["Xem", "Giao dịch"])
        conn = get_db_connection()
        sp_data_raw = conn.execute("SELECT * FROM spare_parts").fetchall()
        sp_data = [dict(r) for r in sp_data_raw]
        pending_requests = conn.execute("SELECT * FROM spare_request_queue WHERE status = 'CHO_DUYET'").fetchall()
        conn.close()

        low_stock_items = [item for item in sp_data if item["quantity"] <= item["min_quantity"]]
        
        sp_kpi1, sp_kpi2, sp_kpi3, sp_kpi4 = st.columns(4)
        with sp_kpi1: st.markdown(f'''<div class="kpi-card-1"><span style="font-size: 15px; font-weight: 800;">Tổng Danh Mục</span><h2 style="margin: 5px 0 0 0;">{len(sp_data)} Loại</h2></div>''', unsafe_allow_html=True)
        with sp_kpi2: st.markdown(f'''<div class="kpi-card-2"><span style="font-size: 15px; font-weight: 800;">Tổng Tồn Kho</span><h2 style="margin: 5px 0 0 0;">{sum(i["quantity"] for i in sp_data)} Cái</h2></div>''', unsafe_allow_html=True)
        with sp_kpi3: st.markdown(f'''<div class="kpi-card-3"><span style="font-size: 15px; font-weight: 800;">Cảnh Báo Thiếu Hàng</span><h2 style="margin: 5px 0 0 0;">{len(low_stock_items)} Loại</h2></div>''', unsafe_allow_html=True)
        with sp_kpi4: st.markdown(f'''<div class="kpi-card-4"><span style="font-size: 15px; font-weight: 800;">Yêu Cầu Chờ Duyệt</span><h2 style="margin: 5px 0 0 0;">{len(pending_requests)} Đơn</h2></div>''', unsafe_allow_html=True)
        
        st.markdown("---")
        if low_stock_items:
            st.error(f"⚠️ **CẢNH BÁO TỒN KHO:** Có {len(low_stock_items)} vật tư dưới mức an toàn: " + ", ".join([f"**{i['part_name']}** ({i['quantity']} {i['unit']})" for i in low_stock_items]))

        sp_menu_options = []
        if "Xem" in user_spare_perms: sp_menu_options.extend(["🔍 Tra Cứu", "📝 Yêu Cầu Của Tôi"])
        if "Giao dịch" in user_spare_perms: sp_menu_options.append("📥 Xuất / Nhập")
        if "Phê duyệt" in user_spare_perms or current_user.get("role") == "Admin": sp_menu_options.append("✅ Phê Duyệt")
        if "Thêm mới" in user_spare_perms: sp_menu_options.append("➕ Thêm Mới")
        if "Xem" in user_spare_perms: sp_menu_options.extend(["📜 Lịch Sử", "📊 Báo Cáo Tiêu Hao"])
        
        # Thêm quyền Xóa Vật Tư
        if "Chỉnh sửa" in user_spare_perms or current_user.get("role", "").lower() == "admin":
            sp_menu_options.append("🗑️ Xóa Vật Tư")

        if not sp_menu_options:
            st.error("🔒 Bạn không có quyền truy cập Kho Spare Part.")
        else:
            current_sp_menu = st.radio("📍 Bảng Điều Khiển Kho:", sp_menu_options, horizontal=True)
            st.write("")

            # ----------------------------------------
            # 1. MỤC TRA CỨU & XUẤT/IN/CHỈNH SỬA
            # ----------------------------------------
            if current_sp_menu == "🔍 Tra Cứu":
                c_s1, c_s2, c_s3, c_s4 = st.columns([2.5, 1.5, 1.5, 1.5])
                with c_s1: search_kw = st.text_input("🔍 Nhập mã, tên, thiết bị...")
                with c_s2: 
                    categories = ["Tất cả nhóm"] + sorted(list(set([i.get("category", "Khác") for i in sp_data])))
                    selected_cat = st.selectbox("Lọc nhóm", categories)
                with c_s3: 
                    locs = ["Tất cả kệ"] + sorted(list(set([i.get("location", "Khác") for i in sp_data])))
                    selected_loc = st.selectbox("Lọc kệ", locs)
                with c_s4:
                    st.write("")
                    st.write("")
                    with st.popover("📷 Tìm bằng ảnh", use_container_width=True):
                        s_img_method = st.radio("Nguồn ảnh:", ["📂 Tải ảnh", "📷 Chụp"], horizontal=True, key="srch_img")
                        s_img = st.file_uploader("Tải ảnh", type=["png","jpg","jpeg"], key="s_up") if s_img_method == "📂 Tải ảnh" else st.camera_input("Chụp ảnh", key="s_cam")
                        search_by_image = False
                        best_match = None
                        if s_img:
                            try:
                                img_bytes = s_img.getvalue()
                                min_diff = float('inf')
                                for item in sp_data:
                                    if item.get('image_url') and item['image_url'].startswith('data:image'):
                                        diff = compare_images_mse(img_bytes, item['image_url'])
                                        if diff < min_diff and diff < 6500:
                                            min_diff = diff
                                            best_match = item
                                search_by_image = True
                            except Exception:
                                st.error("Lỗi thư viện xử lý ảnh (Cần PIL).")

                filtered_sp = sp_data.copy()
                if search_by_image:
                    if best_match:
                        filtered_sp = [best_match]
                        st.success(f"🤖 AI đã nhận diện vật tư tương đồng: **{best_match['part_name']}**")
                    else:
                        filtered_sp = []
                        st.warning("⚠️ Không tìm thấy vật tư tương đồng.")
                else:
                    if selected_cat != "Tất cả nhóm": filtered_sp = [i for i in filtered_sp if i.get("category") == selected_cat]
                    if selected_loc != "Tất cả kệ": filtered_sp = [i for i in filtered_sp if i.get("location") == selected_loc]
                    if search_kw:
                        kw = search_kw.strip().lower()
                        filtered_sp = [i for i in filtered_sp if kw in str(i.get("part_id","")).lower() or kw in str(i.get("part_name","")).lower() or kw in str(i.get("model_applicable","")).lower()]

                st.write("")
                view_mode = st.radio("Chế độ hiển thị:", ["🗂️ Dạng Lưới", "📄 Dạng Bảng"], horizontal=True)

                if view_mode == "📄 Dạng Bảng":
                    st.caption(f"Tìm thấy **{len(filtered_sp)}** vật tư.")
                    df_export = pd.DataFrame(filtered_sp)[['part_id', 'part_name', 'category', 'model_applicable', 'location', 'quantity', 'unit']] if filtered_sp else pd.DataFrame()
                    if not df_export.empty:
                        df_export.columns = ["Mã Vật Tư", "Tên Vật Tư", "Nhóm", "Dùng Cho Máy", "Vị Trí Kệ", "Tồn Kho", "Đơn Vị Tính"]
                        
                        df_all = pd.DataFrame(sp_data)[['part_id', 'part_name', 'category', 'model_applicable', 'location', 'quantity', 'unit']]
                        df_all.columns = ["Mã Vật Tư", "Tên Vật Tư", "Nhóm", "Dùng Cho Máy", "Vị Trí Kệ", "Tồn Kho", "Đơn Vị Tính"]

                        csv_filtered = df_export.to_csv(index=False).encode('utf-8-sig')
                        csv_all = df_all.to_csv(index=False).encode('utf-8-sig')

                        b64_html_filtered = generate_printable_html(df_export, "DANH SÁCH VẬT TƯ (ĐÃ LỌC)")
                        b64_html_all = generate_printable_html(df_all, "DANH SÁCH VẬT TƯ (TẤT CẢ)")

                        c_btn1, c_btn2, c_btn3, _ = st.columns([2.5, 2.5, 2.5, 3.5])
                        with c_btn1:
                            with st.popover("📥 Xuất Dữ Liệu (Đã Lọc)", use_container_width=True):
                                st.download_button("📊 Chọn Excel (CSV)", data=csv_filtered, file_name=f"VatTu_Loc_{date.today()}.csv", mime="text/csv", use_container_width=True)
                                st.markdown(f'<a href="data:text/html;base64,{b64_html_filtered}" download="BaoCao_Loc_{date.today()}.html" style="display: flex; align-items: center; justify-content: center; background: #ffffff; color: #000000; border: 2px solid #facc15; padding: 7px; border-radius: 6px; text-decoration: none; font-weight: 800; margin-top: 5px; height: 38px; box-sizing: border-box;">📄 Chọn PDF</a>', unsafe_allow_html=True)
                        with c_btn2:
                            with st.popover("📥 Xuất All (Tất Cả)", use_container_width=True):
                                st.download_button("📊 Chọn Excel (CSV)", data=csv_all, file_name=f"Kho_Tong_{date.today()}.csv", mime="text/csv", use_container_width=True)
                                st.markdown(f'<a href="data:text/html;base64,{b64_html_all}" download="BaoCao_All_{date.today()}.html" style="display: flex; align-items: center; justify-content: center; background: #ffffff; color: #000000; border: 2px solid #facc15; padding: 7px; border-radius: 6px; text-decoration: none; font-weight: 800; margin-top: 5px; height: 38px; box-sizing: border-box;">📄 Chọn PDF</a>', unsafe_allow_html=True)
                        with c_btn3:
                            components.html('<button onclick="window.parent.print()" style="width: 100%; height: 38px; background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%); color: #000000; border: none; border-radius: 8px; cursor: pointer; font-weight: 900; font-family: sans-serif; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.4);">🖨️ In Ra Giấy</button>', height=45)

                        st.dataframe(df_export, use_container_width=True)

                        if "Chỉnh sửa" in user_spare_perms:
                            st.markdown("---")
                            st.markdown("### ✏️ Chỉnh sửa nhanh từ Bảng Lọc")
                            edit_opt = st.selectbox("Chọn vật tư từ danh sách lọc ở trên để chỉnh sửa:", options=[f"{i['part_id']} - {i['part_name']}" for i in filtered_sp], index=None)
                            if edit_opt:
                                edit_id = edit_opt.split(" - ")[0]
                                item = next(i for i in sp_data if i["part_id"] == edit_id)
                                with st.container(border=True):
                                    q_name = st.text_input("Tên", value=item['part_name'])
                                    c_e1, c_e2, c_e3, c_e4 = st.columns(4)
                                    with c_e1: q_cat = st.text_input("Nhóm", value=item['category'])
                                    with c_e2: q_model = st.text_input("Máy", value=item['model_applicable'])
                                    with c_e3: q_loc = st.text_input("Kệ", value=item['location'])
                                    with c_e4: q_min = st.number_input("Tồn tối thiểu", min_value=1, value=int(item['min_quantity']))
                                    q_unit = st.text_input("ĐVT", value=item['unit'])
                                    
                                    st.markdown("**📸 Cập nhật hình ảnh:**")
                                    img_method_edit = st.radio("Cách đổi ảnh:", ["Bỏ qua", "📂 Tải ảnh lên", "📷 Chụp trực tiếp"], horizontal=True, key=f"tbl_rad_{edit_id}")
                                    q_img = None
                                    if img_method_edit == "📂 Tải ảnh lên": q_img = st.file_uploader("Chọn file ảnh mới", type=["png","jpg","jpeg"], key=f"tbl_up_{edit_id}")
                                    elif img_method_edit == "📷 Chụp trực tiếp": q_img = st.camera_input("Chụp ảnh vật tư mới", key=f"tbl_cam_{edit_id}")
                                    
                                    if st.button("💾 Lưu Cập Nhật", type="primary", use_container_width=True):
                                        img_db = image_to_base64(q_img) if q_img else item.get("image_url")
                                        conn = get_db_connection()
                                        conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, min_quantity=?, unit=?, image_url=? WHERE part_id=?", (q_name, q_cat, q_model, q_loc, q_min, q_unit, img_db, edit_id))
                                        
                                        # Ghi log lịch sử chỉnh sửa
                                        conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), edit_id, "CHINH_SUA", 0, item['quantity'], current_user["name"], f"Cập nhật thông tin chi tiết"))
                                        conn.commit()
                                        conn.close()
                                        st.toast("✅ Cập nhật thành công!", icon="💾")
                                        time.sleep(0.5)
                                        st.rerun()

                else: 
                    for idx in range(0, len(filtered_sp), 3):
                        cols = st.columns(3)
                        for c_idx, item in enumerate(filtered_sp[idx:idx+3]):
                            with cols[c_idx]:
                                with st.container(border=True):
                                    st.image(item.get("image_url") or "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80", use_container_width=True)
                                    st.markdown(f"#### {item['part_name']}")
                                    st.markdown(f"🏷️ **Mã:** `{item['part_id']}` | 📂 {item['category']}")
                                    st.markdown(f"📍 **Vị trí kệ:** `{item['location']}` | ⚙️ **Máy:** {item['model_applicable']}")
                                    st.markdown(f"📦 **Tồn kho:** :green[{item['quantity']} {item['unit']}] (Min: {item['min_quantity']})")
                                    
                                    with st.expander(f"📤 Gửi yêu cầu xuất kho"):
                                        req_q = st.number_input("Số lượng xuất", min_value=1, max_value=max(1, item['quantity']), value=1, key=f"rq_{item['part_id']}")
                                        req_line = st.text_input("Line làm việc*", value=current_user.get("department", "Line-A"), key=f"rl_{item['part_id']}")
                                        req_note = st.text_input("Lý do sử dụng", key=f"rn_{item['part_id']}")
                                        if st.button(f"🚀 Xác Nhận Gửi", key=f"btn_send_{item['part_id']}", type="primary", use_container_width=True):
                                            if req_q > item['quantity']: st.error("Vượt quá tồn kho!")
                                            else:
                                                conn = get_db_connection()
                                                conn.execute("INSERT INTO spare_request_queue (timestamp, part_id, part_name, quantity_requested, requester, line_working, notes, status) VALUES (?,?,?,?,?,?,?,?)",
                                                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item['part_id'], item['part_name'], req_q, f"{current_user['name']} ({current_username})", req_line, req_note, "CHO_DUYET"))
                                                conn.commit()
                                                conn.close()
                                                st.toast("✅ Đã gửi yêu cầu thành công!", icon="🚀")
                                                time.sleep(0.5)
                                                st.rerun()

                                    if "Chỉnh sửa" in user_spare_perms:
                                        with st.popover(f"✏️ Sửa nhanh", use_container_width=True):
                                            st.markdown("**Chỉnh sửa vật tư**")
                                            q_name = st.text_input("Tên", value=item['part_name'], key=f"qn_{item['part_id']}")
                                            q_cat = st.text_input("Nhóm", value=item['category'], key=f"qc_{item['part_id']}")
                                            q_model = st.text_input("Máy", value=item['model_applicable'], key=f"qm_{item['part_id']}")
                                            q_loc = st.text_input("Kệ", value=item['location'], key=f"ql_{item['part_id']}")
                                            q_min = st.number_input("Min", min_value=1, value=int(item['min_quantity']), key=f"qmin_{item['part_id']}")
                                            q_unit = st.text_input("ĐVT", value=item['unit'], key=f"qu_{item['part_id']}")
                                            st.markdown("**📸 Đổi ảnh:**")
                                            img_method_edit = st.radio("Nguồn:", ["Bỏ qua", "📂 Tải lên", "📷 Chụp"], horizontal=True, key=f"rad_{item['part_id']}")
                                            q_img = None
                                            if img_method_edit == "📂 Tải lên": q_img = st.file_uploader("File", type=["png","jpg","jpeg"], key=f"qi_{item['part_id']}")
                                            elif img_method_edit == "📷 Chụp": q_img = st.camera_input("Chụp", key=f"qcam_{item['part_id']}")
                                            
                                            if st.button("💾 Lưu Sửa", key=f"btn_save_edit_{item['part_id']}", use_container_width=True, type="primary"):
                                                img_db = image_to_base64(q_img) if q_img else item.get("image_url")
                                                conn = get_db_connection()
                                                conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, min_quantity=?, unit=?, image_url=? WHERE part_id=?", (q_name, q_cat, q_model, q_loc, q_min, q_unit, img_db, item['part_id']))
                                                
                                                # Ghi log lịch sử chỉnh sửa
                                                conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item['part_id'], "CHINH_SUA", 0, item['quantity'], current_user["name"], f"Sửa nhanh thông tin"))
                                                conn.commit()
                                                conn.close()
                                                st.toast("✅ Cập nhật thành công!", icon="💾")
                                                time.sleep(0.5)
                                                st.rerun()

            # ----------------------------------------
            # 2. XUẤT NHẬP TRỰC TIẾP
            # ----------------------------------------
            elif current_sp_menu == "📥 Xuất / Nhập":
                if sp_data:
                    with st.container(border=True):
                        st.markdown("💡 *Gõ tên hoặc mã vật tư để tìm kiếm và chọn tự động.*")
                        t_opt = st.selectbox("Phụ tùng (Tìm kiếm thông minh)", options=[f"{i['part_id']} - {i['part_name']} (Tồn: {i['quantity']})" for i in sp_data], index=None)
                        t_act = st.radio("Thao tác", ["📥 Nhập Kho (+)", "📤 Xuất Kho (-)"], horizontal=True)
                        t_q = st.number_input("Số lượng", min_value=1, value=1)
                        t_n = st.text_input("Ghi chú")
                        if st.button("💾 Thực Hiện Giao Dịch", type="primary", use_container_width=True):
                            if not t_opt: show_popup_message("CẢNH BÁO", "Vui lòng chọn vật tư!", "⚠️")
                            else:
                                t_id = t_opt.split(" - ")[0]
                                cur = next(i for i in sp_data if i["part_id"] == t_id)
                                cur_q = cur["quantity"]
                                if "📤" in t_act and t_q > cur_q: show_popup_message("LỖI", "Số lượng xuất vượt quá tồn kho!", "❌")
                                else:
                                    new_q = cur_q + t_q if "📥" in t_act else cur_q - t_q
                                    conn = get_db_connection()
                                    conn.execute("UPDATE spare_parts SET quantity=? WHERE part_id=?", (new_q, t_id))
                                    conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), t_id, "NHAP" if "📥" in t_act else "XUAT", t_q, new_q, current_user["name"], t_n))
                                    conn.commit()
                                    conn.close()
                                    show_popup_message("THÀNH CÔNG", f"Đã lưu! Tồn kho mới: {new_q} {cur['unit']}", "📦")

            # ----------------------------------------
            # 3. YÊU CẦU CỦA TÔI
            # ----------------------------------------
            elif current_sp_menu == "📝 Yêu Cầu Của Tôi":
                conn = get_db_connection()
                my_queue = conn.execute("SELECT * FROM spare_request_queue WHERE requester LIKE ? ORDER BY id DESC", (f"%({current_username})%",)).fetchall()
                conn.close()
                if my_queue:
                    df_my_req = pd.DataFrame([dict(r) for r in my_queue])[['id', 'timestamp', 'part_id', 'part_name', 'quantity_requested', 'line_working', 'status']]
                    df_my_req.columns = ["Mã Phiếu", "Thời Gian", "Mã VT", "Tên VT", "SL Yêu Cầu", "Line", "Trạng Thái"]
                    st.dataframe(df_my_req, use_container_width=True)
                else:
                    st.info("Chưa có yêu cầu xuất kho nào.")

            # ----------------------------------------
            # 4. PHÊ DUYỆT
            # ----------------------------------------
            elif current_sp_menu == "✅ Phê Duyệt":
                conn = get_db_connection()
                queue_list = conn.execute("SELECT * FROM spare_request_queue WHERE status = 'CHO_DUYET' ORDER BY id DESC").fetchall()
                conn.close()
                if queue_list:
                    for req in queue_list:
                        with st.container(border=True):
                            r_cols = st.columns([3, 2, 2])
                            with r_cols[0]:
                                st.markdown(f"**Vật tư:** `{req['part_id']}` - **{req['part_name']}**")
                                st.markdown(f"📦 **Số lượng xin xuất:** `{req['quantity_requested']}`")
                            with r_cols[1]:
                                st.markdown(f"👤 **Người yêu cầu:** {req['requester']}")
                                st.markdown(f"🏭 **Line:** `{req['line_working']}`")
                            with r_cols[2]:
                                st.markdown(f"📝 **Lý do:** {req['notes']}")
                            btn_c1, btn_c2 = st.columns(2)
                            with btn_c1:
                                if st.button("✅ Phê Duyệt", key=f"app_{req['id']}", use_container_width=True, type="primary"):
                                    conn = get_db_connection()
                                    p_item = conn.execute("SELECT * FROM spare_parts WHERE part_id = ?", (req['part_id'],)).fetchone()
                                    if p_item and p_item['quantity'] >= req['quantity_requested']:
                                        new_qty = p_item['quantity'] - req['quantity_requested']
                                        conn.execute("UPDATE spare_parts SET quantity = ? WHERE part_id = ?", (new_qty, req['part_id']))
                                        conn.execute("UPDATE spare_request_queue SET status = 'DA_DUYET' WHERE id = ?", (req['id'],))
                                        conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), req['part_id'], "XUAT", req['quantity_requested'], new_qty, f"{current_user['name']} (Duyệt cho {req['requester']})", req['notes']))
                                        conn.commit()
                                        conn.close()
                                        st.rerun()
                                    else:
                                        conn.close()
                                        show_popup_message("LỖI", "Tồn kho không đủ!", "❌")
                            with btn_c2:
                                if st.button("❌ Từ Chối", key=f"rej_{req['id']}", use_container_width=True):
                                    conn = get_db_connection()
                                    conn.execute("UPDATE spare_request_queue SET status = 'TU_CHOI' WHERE id = ?", (req['id'],))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
                else: st.info("Không có yêu cầu chờ duyệt.")

            # ----------------------------------------
            # 5. THÊM MỚI (ĐÃ BỔ SUNG GHI LOG ĐẦY ĐỦ)
            # ----------------------------------------
            elif current_sp_menu == "➕ Thêm Mới":
                st.markdown("### 🛠️ Thêm Mới Từng Vật Tư")
                with st.container(border=True):
                    n_id = st.text_input("Mã phụ tùng*", key="add_id")
                    n_name = st.text_input("Tên phụ tùng*", key="add_name")
                    c_n1, c_n2 = st.columns(2)
                    with c_n1: n_cat = st.text_input("Nhóm", value="Cơ khí", key="add_cat")
                    with c_n2: n_mod = st.text_input("Máy áp dụng", value="Tất cả", key="add_mod")
                    c_n3, c_n4, c_n5 = st.columns(3)
                    with c_n3: n_loc = st.text_input("Vị trí kệ", value="Kệ A", key="add_loc")
                    with c_n4: n_qty = st.number_input("Tồn ban đầu", min_value=0, value=10, key="add_qty")
                    with c_n5: n_min = st.number_input("Tồn tối thiểu", min_value=1, value=5, key="add_min")
                    n_unit = st.text_input("ĐVT", value="Cái", key="add_unit")
                    st.markdown("**📸 Hình ảnh vật tư:**")
                    img_method_add = st.radio("Cách thêm ảnh:", ["📂 Tải ảnh lên", "📷 Chụp trực tiếp"], horizontal=True)
                    n_file = st.file_uploader("Chọn file ảnh", type=["png","jpg","jpeg"]) if img_method_add == "📂 Tải ảnh lên" else st.camera_input("Chụp ảnh trực tiếp")
                    if st.button("💾 Lưu Mã Phụ Tùng Mới", key="btn_save_new_sp", type="primary", use_container_width=True):
                        if not n_id or not n_name: show_popup_message("LỖI", "Nhập đủ Mã và Tên!", "❌")
                        else:
                            img_save = image_to_base64(n_file) if n_file else "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80"
                            conn = get_db_connection()
                            exists = conn.execute("SELECT part_id FROM spare_parts WHERE part_id=?", (n_id,)).fetchone()
                            if exists:
                                show_popup_message("LỖI", f"Mã phụ tùng '{n_id}' đã tồn tại trong kho!", "❌")
                            else:
                                conn.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", (n_id, n_name, n_cat, n_mod, n_loc, n_qty, n_min, n_unit, img_save))
                                # Ghi log tạo mới vật tư
                                conn.execute(
                                    "INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), n_id, "TAO_MOI", n_qty, n_qty, current_user["name"], f"Tạo mới mã vật tư: {n_name}")
                                )
                                conn.commit()
                                show_popup_message("THÀNH CÔNG", f"Đã thêm {n_name}!", "🎉")
                            conn.close()
                
                st.markdown("---")
                st.markdown("### 📁 Cập Nhật Dữ Luệu Nhanh (Từ File Excel/CSV)")
                with st.container(border=True):
                    st.info("💡 **Mẹo:** Tải file mẫu về, điền dữ liệu và upload lên để hệ thống tự động tạo hàng loạt vật tư vào kho.")
                    df_template = pd.DataFrame(columns=["part_id", "part_name", "category", "model_applicable", "location", "quantity", "min_quantity", "unit"])
                    csv_template = df_template.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 Tải File Mẫu (CSV)", data=csv_template, file_name="Mau_Nhap_Kho.csv", mime="text/csv")
                    
                    uploaded_file = st.file_uploader("Tải lên file dữ liệu (.csv, .xlsx)", type=["csv", "xlsx"])
                    if st.button("🚀 Chạy Cập Nhật Tự Động", type="primary"):
                        if uploaded_file is not None:
                            try:
                                if uploaded_file.name.endswith('.csv'): df_import = pd.read_csv(uploaded_file)
                                else: df_import = pd.read_excel(uploaded_file)
                                
                                required_cols = ["part_id", "part_name"]
                                if not all(col in df_import.columns for col in required_cols):
                                    st.error(f"Lỗi: File thiếu các cột bắt buộc: {required_cols}. Hãy tải file mẫu để xem định dạng chuẩn.")
                                else:
                                    conn = get_db_connection()
                                    success_cnt = 0
                                    for idx, row in df_import.iterrows():
                                        p_id = str(row.get("part_id", "")).strip()
                                        p_name = str(row.get("part_name", "")).strip()
                                        if not p_id or not p_name or str(p_id) == 'nan': continue
                                        
                                        p_cat = str(row.get("category", "Khác")) if pd.notna(row.get("category")) else "Khác"
                                        p_mod = str(row.get("model_applicable", "Tất cả")) if pd.notna(row.get("model_applicable")) else "Tất cả"
                                        p_loc = str(row.get("location", "Kho")) if pd.notna(row.get("location")) else "Kho"
                                        
                                        try: p_qty = int(row.get("quantity", 0))
                                        except: p_qty = 0
                                        try: p_min = int(row.get("min_quantity", 5))
                                        except: p_min = 5
                                        
                                        p_unit = str(row.get("unit", "Cái")) if pd.notna(row.get("unit")) else "Cái"
                                        
                                        exists = conn.execute("SELECT part_id, quantity FROM spare_parts WHERE part_id=?", (p_id,)).fetchone()
                                        if exists:
                                            old_q = exists["quantity"]
                                            diff_q = p_qty - old_q
                                            conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, quantity=?, min_quantity=?, unit=? WHERE part_id=?", 
                                                         (p_name, p_cat, p_mod, p_loc, p_qty, p_min, p_unit, p_id))
                                            # Ghi log cập nhật từ Excel
                                            conn.execute(
                                                "INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_id, "CAP_NHAT_EXCEL", diff_q, p_qty, current_user["name"], "Cập nhật hàng loạt từ file Excel/CSV")
                                            )
                                        else:
                                            conn.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", 
                                                         (p_id, p_name, p_cat, p_mod, p_loc, p_qty, p_min, p_unit, None))
                                            # Ghi log tạo mới từ Excel
                                            conn.execute(
                                                "INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_id, "TAO_MOI_EXCEL", p_qty, p_qty, current_user["name"], f"Tạo mới từ file Excel/CSV: {p_name}")
                                            )
                                        success_cnt += 1
                                    
                                    conn.commit()
                                    conn.close()
                                    st.success(f"✅ Đã thêm/cập nhật thành công {success_cnt} vật tư!")
                                    time.sleep(1.5)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi khi đọc file. Vui lòng kiểm tra lại định dạng: {e}")
                        else:
                            st.warning("Vui lòng đính kèm một file Excel hoặc CSV để hệ thống đọc dữ liệu.")

            # ----------------------------------------
            # 6. LỊCH SỬ
            # ----------------------------------------
            elif current_sp_menu == "📜 Lịch Sử":
                conn = get_db_connection()
                logs = conn.execute("SELECT * FROM spare_part_logs ORDER BY id DESC LIMIT 200").fetchall()
                conn.close()
                if logs: 
                    df_log = pd.DataFrame([dict(l) for l in logs])
                    df_log.columns = ["ID", "Thời Gian", "Mã VT", "Thao Tác", "SL Thay Đổi", "Tồn Mới", "Người Thực Hiện", "Ghi Chú"]
                    
                    c_log1, c_log2, _ = st.columns([2, 2, 6])
                    csv_data = df_log.to_csv(index=False).encode('utf-8-sig')
                    b64_html = generate_printable_html(df_log, "LỊCH SỬ GIAO DỊCH KHO")
                    
                    with c_log1:
                        with st.popover("📥 Xuất Lịch Sử", use_container_width=True):
                            st.download_button("📊 Chọn Excel (CSV)", data=csv_data, file_name=f"LichSuGiaoDich_{date.today()}.csv", mime="text/csv", use_container_width=True)
                            st.markdown(f'<a href="data:text/html;base64,{b64_html}" download="LichSu_{date.today()}.html" style="display: flex; align-items: center; justify-content: center; background: #ffffff; color: #000000; border: 2px solid #facc15; padding: 7px; border-radius: 6px; text-decoration: none; font-weight: 800; margin-top: 5px; height: 38px; box-sizing: border-box;">📄 Chọn PDF</a>', unsafe_allow_html=True)
                    with c_log2:
                        components.html('<button onclick="window.parent.print()" style="width: 100%; height: 38px; background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%); color: #000000; border: none; border-radius: 8px; cursor: pointer; font-weight: 900; font-family: sans-serif; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.5);">🖨️ In Ra Giấy</button>', height=45)
                    st.dataframe(df_log, use_container_width=True)
                else: st.info("Chưa có lịch sử giao dịch nào.")

            # ----------------------------------------
            # 7. XÓA VẬT TƯ (TÍNH NĂNG MỚI)
            # ----------------------------------------
            elif current_sp_menu == "🗑️ Xóa Vật Tư":
                st.markdown("### 🗑️ XÓA VẬT TƯ KHỎI HỆ THỐNG")
                if sp_data:
                    with st.container(border=True):
                        st.error("⚠️ **LƯU Ý:** Hành động này sẽ xóa hoàn toàn vật tư khỏi danh mục kho. Xin hãy cân nhắc kỹ!")
                        
                        # Hiển thị list để chọn vật tư
                        del_opt = st.selectbox(
                            "Chọn vật tư không còn sử dụng để xóa:", 
                            options=[f"{i['part_id']} - {i['part_name']} (Tồn: {i['quantity']})" for i in sp_data], 
                            index=None
                        )
                        
                        if st.button("🚨 XÁC NHẬN RÚT KHỎI KHO", type="primary", use_container_width=True):
                            if not del_opt:
                                show_popup_message("LỖI", "Vui lòng chọn một vật tư trước khi nhấn nút xóa!", "❌")
                            else:
                                del_id = del_opt.split(" - ")[0]
                                cur = next(i for i in sp_data if i["part_id"] == del_id)
                                
                                conn = get_db_connection()
                                conn.execute("DELETE FROM spare_parts WHERE part_id=?", (del_id,))
                                
                                # Ghi lại log lịch sử khi XÓA
                                conn.execute("INSERT INTO spare_part_logs (timestamp, part_id, action_type, quantity_changed, remaining_qty, user_action, notes) VALUES (?,?,?,?,?,?,?)",
                                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), del_id, "XOA_VAT_TU", 0, 0, current_user["name"], f"Xóa hoàn toàn khỏi kho (Tồn cũ: {cur['quantity']})"))
                                conn.commit()
                                conn.close()
                                show_popup_message("THÀNH CÔNG", f"Đã xóa hoàn toàn vật tư **{cur['part_name']}** khỏi hệ thống!", "🗑️")
                else:
                    st.info("Danh mục kho đang trống, không có gì để xóa.")

            # ----------------------------------------
            # 8. BÁO CÁO & THỐNG KÊ TIÊU HAO (TÍNH NĂNG MỚI)
            # ----------------------------------------
            elif current_sp_menu == "📊 Báo Cáo Tiêu Hao":
                st.markdown("### 📊 DASHBOARD THỐNG KÊ LƯỢNG TIÊU HAO (XUẤT KHO)")
                
                conn = get_db_connection()
                # Chỉ lấy những log có hành động là XUAT
                logs = conn.execute("SELECT * FROM spare_part_logs WHERE action_type = 'XUAT'").fetchall()
                conn.close()
                
                if not logs:
                    st.info("Chưa có dữ liệu xuất kho để tạo thống kê.")
                else:
                    df_logs = pd.DataFrame([dict(l) for l in logs])
                    df_logs['timestamp'] = pd.to_datetime(df_logs['timestamp'])
                    df_logs['date'] = df_logs['timestamp'].dt.date
                    df_logs['month'] = df_logs['timestamp'].dt.to_period('M')
                    
                    # Ghép với tên vật tư hiện tại
                    df_parts = pd.DataFrame(sp_data)[['part_id', 'part_name']] if sp_data else pd.DataFrame(columns=['part_id', 'part_name'])
                    if not df_parts.empty:
                        df_logs = df_logs.merge(df_parts, on='part_id', how='left')
                    else:
                        df_logs['part_name'] = "Không xác định"
                    
                    # Điền tên đối với các mã vật tư đã bị xóa
                    df_logs['part_name'] = df_logs['part_name'].fillna("Vật tư đã bị xóa khỏi hệ thống")
                    
                    # Mốc thời gian
                    now = datetime.now()
                    last_30_days = now.date() - pd.Timedelta(days=30)
                    current_month = now.to_period('M')
                    
                    # Chia luồng dữ liệu
                    df_30_days = df_logs[df_logs['date'] >= last_30_days]
                    df_current_month = df_logs[df_logs['month'] == current_month]
                    
                    tab1, tab2, tab3 = st.tabs([
                        "📉 Tiêu hao 30 ngày qua (Update Hàng Ngày)", 
                        "🏆 TOP 50 Tiêu Hao (30 Ngày)", 
                        "📅 Thống Kê Theo Tháng Thực Tế"
                    ])
                    
                    with tab1:
                        st.markdown("#### Xu hướng vật tư tiêu hao (Cập nhật tự động theo từng ngày)")
                        if not df_30_days.empty:
                            daily_export = df_30_days.groupby('date')['quantity_changed'].sum().reset_index()
                            
                            # Biểu đồ Plotly hiển thị xu hướng
                            fig1 = go.Figure()
                            fig1.add_trace(go.Bar(x=daily_export['date'], y=daily_export['quantity_changed'], marker_color='#facc15', name="Lượng tiêu hao"))
                            fig1.add_trace(go.Scatter(x=daily_export['date'], y=daily_export['quantity_changed'], mode='lines+markers', line=dict(color='#ef4444', width=2), name="Đường xu hướng"))
                            fig1.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'), hovermode="x unified")
                            st.plotly_chart(fig1, use_container_width=True)
                            
                            # Bảng Highlight dữ liệu cao nhất
                            daily_export.columns = ['Thời gian (Ngày)', 'Tổng Số Lượng Đã Xuất']
                            styled_df1 = daily_export.style.highlight_max(subset=['Tổng Số Lượng Đã Xuất'], color='#ef4444')
                            st.dataframe(styled_df1, use_container_width=True)
                        else:
                            st.info("Hệ thống chưa ghi nhận lần xuất kho nào trong 30 ngày qua.")
                    
                    with tab2:
                        st.markdown("#### TOP 50 Vật tư tiêu tốn nhiều nhất (Trong 30 ngày qua)")
                        if not df_30_days.empty:
                            top_50 = df_30_days.groupby(['part_id', 'part_name'])['quantity_changed'].sum().reset_index()
                            top_50 = top_50.sort_values(by='quantity_changed', ascending=False).head(50)
                            
                            # Biểu đồ thanh ngang
                            fig2 = go.Figure(go.Bar(
                                x=top_50['quantity_changed'][::-1],
                                y=top_50['part_name'][::-1],
                                orientation='h',
                                marker_color='#3b82f6',
                                text=top_50['quantity_changed'][::-1],
                                textposition='auto'
                            ))
                            fig2.update_layout(height=max(400, len(top_50)*28), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                            st.plotly_chart(fig2, use_container_width=True)
                            
                            # Bảng Highlight
                            top_50.columns = ['Mã Phụ Tùng', 'Tên Vật Tư', 'Tổng SL Xuất']
                            styled_df2 = top_50.style.highlight_max(subset=['Tổng SL Xuất'], color='#ef4444')
                            st.dataframe(styled_df2, use_container_width=True)
                        else:
                            st.info("Hệ thống chưa ghi nhận lần xuất kho nào trong 30 ngày qua.")
                    
                    with tab3:
                        st.markdown(f"#### Báo cáo tiêu hao tháng {now.month}/{now.year} (Dữ liệu thời gian thực)")
                        if not df_current_month.empty:
                            monthly_stat = df_current_month.groupby(['part_id', 'part_name'])['quantity_changed'].sum().reset_index()
                            monthly_stat = monthly_stat.sort_values(by='quantity_changed', ascending=False)
                            
                            c_pie, c_tab = st.columns([4, 6])
                            with c_pie:
                                # Biểu đồ tròn TOP 10 Tháng
                                fig3 = go.Figure(go.Pie(
                                    labels=monthly_stat['part_name'].head(10),
                                    values=monthly_stat['quantity_changed'].head(10),
                                    hole=0.4,
                                    marker=dict(colors=['#facc15', '#eab308', '#ca8a04', '#a16207', '#3b82f6', '#2563eb', '#1d4ed8', '#1e40af'])
                                ))
                                fig3.update_layout(title="Cơ Cấu Vật Tư (TOP 10 Tháng)", legend=dict(orientation="h", yanchor="bottom", y=-0.2), paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                                st.plotly_chart(fig3, use_container_width=True)
                            
                            with c_tab:
                                # Bảng thống kê toàn tháng Highlight
                                monthly_stat.columns = ['Mã Phụ Tùng', 'Tên Vật Tư', 'Tổng Số Lượng Đã Xuất']
                                styled_df3 = monthly_stat.style.highlight_max(subset=['Tổng Số Lượng Đã Xuất'], color='#ef4444')
                                st.dataframe(styled_df3, use_container_width=True, height=450)
                        else:
                            st.info(f"Trong tháng {now.month}/{now.year} chưa có phát sinh tiêu hao xuất kho.")

    # =========================================================================
    # TRANG 3: QUẢN LÝ MÁY MÓC
    # =========================================================================
    elif selected_menu == "🏭 Quản Lý Máy Móc":
        st.markdown("## ⚙️ HỆ THỐNG ME-AMP - QUẢN LÝ THIẾT BỊ")
        st.markdown("---")
        user_m_perms = current_user.get("machine_perms", ["Xem"])
        m_menu_options = []
        if "Xem" in user_m_perms: m_menu_options.append("📋 Danh Sách Máy Móc")
        if "Thêm mới" in user_m_perms: m_menu_options.append("➕ Thêm Mới")
        if "Chỉnh sửa" in user_m_perms: m_menu_options.append("✏️ Chỉnh Sửa")
        if "Xóa" in user_m_perms: m_menu_options.append("🗑️ Xóa")
        if not m_menu_options:
            st.error("🔒 Bạn không có quyền truy cập Quản Lý Máy Móc.")
        else:
            current_m_menu = st.radio("📍 Điều Khiển Thiết Bị:", m_menu_options, horizontal=True)
            st.write("")

            if current_m_menu == "📋 Danh Sách Máy Móc":
                if machine_db:
                    df_m = pd.DataFrame(machine_db)
                    df_m.columns = ["Mã Máy", "Tên Máy", "Line", "URL", "File Mẫu", "Có File"]
                    st.dataframe(df_m, use_container_width=True)
                else:
                    st.info("Chưa có dữ liệu máy móc.")
            
            elif current_m_menu == "➕ Thêm Mới":
                with st.form("add_machine_form"):
                    st.subheader("Tạo Máy Mới")
                    m_id = st.text_input("Mã Máy*")
                    m_name = st.text_input("Tên Máy*")
                    m_line = st.text_input("Dây chuyền (Line)*")
                    m_url = st.text_input("Đường dẫn máy (URL)")
                    m_file = st.text_input("File mẫu dữ liệu")
                    if st.form_submit_button("Lưu mới", type="primary"):
                        if not m_id or not m_name or not m_line:
                            st.error("Vui lòng nhập đủ các trường bắt buộc (*)")
                        else:
                            conn = get_db_connection()
                            exists = conn.execute("SELECT id FROM machines WHERE id=?", (m_id,)).fetchone()
                            if exists: st.error("Mã máy đã tồn tại!")
                            else:
                                conn.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", (m_id, m_name, m_line, m_url, m_file, 1 if m_file else 0))
                                conn.commit()
                                conn.close()
                                st.toast("✅ Đã thêm máy mới!", icon="🚀")
                                time.sleep(0.5)
                                st.rerun()

            elif current_m_menu == "✏️ Chỉnh Sửa":
                if machine_db:
                    m_opt = st.selectbox("Chọn máy cần sửa:", [f"{m['id']} - {m['name']}" for m in machine_db])
                    if m_opt:
                        m_id_edit = m_opt.split(" - ")[0]
                        cur_m = next(m for m in machine_db if m["id"] == m_id_edit)
                        allowed_fields = current_user.get("editable_machine_fields", [])
                        is_admin = current_user.get("role", "").lower() == "admin"
                        with st.form("edit_machine_form"):
                            st.subheader(f"Chỉnh sửa: {cur_m['name']}")
                            dis_name = not is_admin and "Tên máy" not in allowed_fields
                            dis_line = not is_admin and "Dây chuyền (Line)" not in allowed_fields
                            dis_url = not is_admin and "Đường dẫn máy" not in allowed_fields
                            dis_file = not is_admin and "File mẫu dữ liệu" not in allowed_fields
                            e_m_name = st.text_input("Tên Máy", value=cur_m['name'], disabled=dis_name)
                            e_m_line = st.text_input("Dây chuyền (Line)", value=cur_m['line'], disabled=dis_line)
                            e_m_url = st.text_input("Đường dẫn máy (URL)", value=cur_m['url'], disabled=dis_url)
                            e_m_file = st.text_input("File mẫu dữ liệu", value=cur_m['template_file'], disabled=dis_file)
                            if st.form_submit_button("Lưu thay đổi", type="primary"):
                                conn = get_db_connection()
                                conn.execute("UPDATE machines SET name=?, line=?, url=?, template_file=?, has_file=? WHERE id=?", (e_m_name, e_m_line, e_m_url, e_m_file, 1 if e_m_file else 0, m_id_edit))
                                conn.commit()
                                conn.close()
                                st.toast("✅ Đã cập nhật thành công!", icon="💾")
                                time.sleep(0.5)
                                st.rerun()
                else: st.info("Chưa có máy móc nào.")

            elif current_m_menu == "🗑️ Xóa":
                if machine_db:
                    del_m_opt = st.selectbox("Chọn máy cần xóa:", [f"{m['id']} - {m['name']}" for m in machine_db], key="del_m")
                    if st.button("🗑️ Xác nhận xóa", type="primary", use_container_width=True):
                        m_id_del = del_m_opt.split(" - ")[0]
                        conn = get_db_connection()
                        conn.execute("DELETE FROM machines WHERE id=?", (m_id_del,))
                        conn.commit()
                        conn.close()
                        st.toast("✅ Đã xóa máy!", icon="🗑️")
                        time.sleep(0.5)
                        st.rerun()

    # =========================================================================
    # TRANG 4: QUẢN LÝ TÀI KHOẢN
    # =========================================================================
    elif selected_menu == "👤 Quản Lý Tài Khoản":
        st.markdown("## ⚙️ HỆ THỐNG ME-AMP - QUẢN LÝ TÀI KHOẢN")
        st.markdown("---")

        opt_pages = current_user.get("allowed_pages", [])
        opt_m_perms = current_user.get("machine_perms", [])
        opt_edits = current_user.get("editable_machine_fields", [])
        opt_s_perms = current_user.get("spare_perms", [])

        conn = get_db_connection()
        if current_username.lower() != "admin":
            users_db = conn.execute("SELECT * FROM users WHERE LOWER(username) != 'admin'").fetchall()
        else:
            users_db = conn.execute("SELECT * FROM users").fetchall()
        conn.close()

        acc_menu_options = ["📋 Danh Sách Tài Khoản", "➕ Tạo Mới", "✏️ Chỉnh Sửa", "🔑 Cấp Lại Mật Khẩu", "🗑️ Xóa", "🛡️ Nhật Ký Bảo Mật"]
        current_acc_menu = st.radio("📍 Quản Trị:", acc_menu_options, horizontal=True)
        st.write("")

        if current_acc_menu == "📋 Danh Sách Tài Khoản":
            st.subheader("📋 Danh Sách Người Dùng & Quyền Hạn Chi Tiết")
            display_data = []
            for u in users_db:
                pages_list = json.loads(u["allowed_pages"]) if u["allowed_pages"] else []
                display_data.append({
                    "Tài khoản": u["username"], "Họ và Tên": u["name"],
                    "Bộ phận": u["department"], "Chức vụ": u["position"],
                    "Quyền (Role)": u["role"], "Các mục truy cập": ", ".join(pages_list)
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)

            st.markdown("---")
            st.markdown("### 🔍 Xem Nổi Bật Thông Tin & Quyền Hạn Tài Khoản")
            if users_db:
                selected_highlight_user = st.selectbox("Chọn tài khoản để xem chi tiết nổi bật", [u["username"] for u in users_db])
                if selected_highlight_user:
                    sel_u_obj = next(u for u in users_db if u["username"] == selected_highlight_user)
                    p_list = json.loads(sel_u_obj["allowed_pages"]) if sel_u_obj["allowed_pages"] else []
                    m_perms = json.loads(sel_u_obj["machine_perms"]) if sel_u_obj["machine_perms"] else []
                    s_perms = json.loads(sel_u_obj["spare_perms"]) if sel_u_obj["spare_perms"] else []

                    st.markdown(f"""
                        <div class="highlight-box">
                            <h3 style="color: #facc15; margin-top: 0; text-shadow: 1px 1px 3px #000;">👤 Tài khoản: {sel_u_obj['username'].upper()} ({sel_u_obj['name']})</h3>
                            <p><b>🏢 Bộ phận:</b> {sel_u_obj['department']} &nbsp;|&nbsp; <b>💼 Chức vụ:</b> {sel_u_obj['position']} &nbsp;|&nbsp; <b>🔑 Phân quyền:</b> {sel_u_obj['role']}</p>
                            <hr style="border-color: #facc15;">
                            <p><b>📌 Các mục phần mềm được truy cập:</b> <span style="color: #fef08a;">{", ".join(p_list)}</span></p>
                            <p><b>⚙️ Quyền quản lý máy móc:</b> {", ".join(m_perms)}</p>
                            <p><b>📦 Quyền chi tiết kho Spare Part:</b> {", ".join(s_perms)}</p>
                        </div>
                    """, unsafe_allow_html=True)

        elif current_acc_menu == "➕ Tạo Mới":
            with st.form("form_add_user"):
                st.info("🔐 Hệ thống có thể tự động tạo mật khẩu mạnh nếu bạn bỏ trống ô Mật khẩu.")
                c1, c2 = st.columns(2)
                with c1:
                    a_username = st.text_input("Tên tài khoản*")
                    a_password = st.text_input("Mật khẩu (Bỏ trống để tự động tạo ngẫu nhiên)")
                    a_fullname = st.text_input("Họ và Tên")
                with c2:
                    a_dept = st.text_input("Bộ phận", value="Sản Xuất")
                    a_pos = st.text_input("Chức vụ", value="Nhân Viên")
                    a_role = st.text_input("Quyền*", value="Operator")

                a_pages = st.multiselect("Trang truy cập", opt_pages, default=[p for p in ["🎛️ Dashboard OEE"] if p in opt_pages])
                a_m_perms = st.multiselect("Quyền thiết bị (Máy móc)", opt_m_perms, default=[p for p in ["Xem"] if p in opt_m_perms])
                a_edit_fields = st.multiselect("Cột máy được sửa", opt_edits, default=[p for p in ["Đường dẫn máy"] if p in opt_edits])
                a_spare_perms = st.multiselect("Quyền chi tiết Kho Spare Part", opt_s_perms, default=[p for p in ["Xem", "Giao dịch"] if p in opt_s_perms])

                if st.form_submit_button("➕ Tạo Mới", use_container_width=True):
                    if not validate_username(a_username):
                        show_popup_message("LỖI", "Tên đăng nhập 3-20 ký tự (Không chứa dấu, khoảng trắng)!", icon="❌")
                    elif a_role.strip().lower() == "admin" and current_username.lower() != "admin":
                        show_popup_message("LỖI", "Bạn không có quyền tạo tài khoản cấp Admin!", icon="❌")
                    else:
                        final_password = a_password if a_password.strip() else generate_strong_password()
                        is_valid, msg = validate_password_strength(final_password)
                        if not is_valid:
                            show_popup_message("MẬT KHẨU YẾU", msg, icon="❌")
                        elif any(u["username"] == a_username.lower() for u in users_db):
                            show_popup_message("LỖI", "Tài khoản đã tồn tại!", icon="⚠️")
                        else:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO users (username, password_hash, name, department, position, role, allowed_pages, machine_perms, editable_machine_fields, spare_perms, last_active) VALUES (?,?,?,?,?,?,?,?,?,?,?)", 
                                        (a_username.lower(), hash_password(final_password), a_fullname, a_dept, a_pos, a_role.strip(), json.dumps(a_pages), json.dumps(a_m_perms), json.dumps(a_edit_fields), json.dumps(a_spare_perms), 0))
                            conn.commit()
                            conn.close()
                            log_security_event(st.session_state["username"], f"TẠO USER ({a_username})", "Thành công")
                            show_popup_message("THÀNH CÔNG", f"Đã tạo tài khoản **{a_username}**!\n\n🔑 **Mật khẩu là:** `{final_password}`", icon="👤")

        elif current_acc_menu == "✏️ Chỉnh Sửa":
            if users_db:
                target_user = st.selectbox("Chọn tài khoản cần sửa", [u["username"] for u in users_db], key="sel_edit_u")
                cur_u = next(u for u in users_db if u["username"] == target_user)
                disable_perms = (target_user == current_username and current_username.lower() != "admin")

                with st.form("form_edit_user"):
                    if disable_perms:
                        st.info("⚠️ Tính năng tự phân quyền bị vô hiệu hóa vì bạn không phải là Admin.")
                    e_fullname = st.text_input("Họ và Tên", value=cur_u["name"])
                    c1, c2, c3 = st.columns(3)
                    with c1: e_dept = st.text_input("Bộ phận", value=cur_u["department"])
                    with c2: e_pos = st.text_input("Chức vụ", value=cur_u["position"])
                    with c3: e_role = st.text_input("Quyền (Role)", value=cur_u["role"], disabled=disable_perms)

                    target_pages = json.loads(cur_u["allowed_pages"]) if cur_u["allowed_pages"] else []
                    target_m_perms = json.loads(cur_u["machine_perms"]) if cur_u["machine_perms"] else []
                    target_edits = json.loads(cur_u["editable_machine_fields"]) if cur_u["editable_machine_fields"] else []
                    target_s_perms = json.loads(cur_u["spare_perms"]) if cur_u["spare_perms"] else ["Xem", "Giao dịch"]

                    e_pages = st.multiselect("Trang truy cập", opt_pages, default=[p for p in target_pages if p in opt_pages], disabled=disable_perms)
                    e_m_perms = st.multiselect("Quyền thiết bị (Máy móc)", opt_m_perms, default=[p for p in target_m_perms if p in opt_m_perms], disabled=disable_perms)
                    e_edits = st.multiselect("Cột máy được sửa", opt_edits, default=[p for p in target_edits if p in opt_edits], disabled=disable_perms)
                    e_spare_perms = st.multiselect("Quyền chi tiết Kho Spare Part", opt_s_perms, default=[p for p in target_s_perms if p in opt_s_perms], disabled=disable_perms)

                    if st.form_submit_button("💾 Lưu Thay Đổi", use_container_width=True):
                        if not disable_perms and e_role.strip().lower() == "admin" and current_username.lower() != "admin":
                            show_popup_message("LỖI", "Bạn không có quyền nâng cấp tài khoản này lên Admin!", icon="❌")
                        else:
                            conn = get_db_connection()
                            if disable_perms:
                                conn.execute("""UPDATE users SET name=?, department=?, position=? WHERE username=?""", (e_fullname, e_dept, e_pos, target_user))
                            else:
                                conn.execute("""UPDATE users SET name=?, department=?, position=?, role=?, allowed_pages=?, machine_perms=?, editable_machine_fields=?, spare_perms=? WHERE username=?""", 
                                             (e_fullname, e_dept, e_pos, e_role.strip(), json.dumps(e_pages), json.dumps(e_m_perms), json.dumps(e_edits), json.dumps(e_spare_perms), target_user))
                            conn.commit()
                            conn.close()

                            if target_user == st.session_state["username"]:
                                st.session_state["user_info"].update({"name": e_fullname, "department": e_dept, "position": e_pos})
                                if not disable_perms:
                                    st.session_state["user_info"].update({"role": e_role, "allowed_pages": e_pages, "machine_perms": e_m_perms, "editable_machine_fields": e_edits, "spare_perms": e_spare_perms})
                            show_popup_message("THÀNH CÔNG", f"Đã cập nhật thông tin cho **{target_user}**!", icon="💾")

        elif current_acc_menu == "🔑 Cấp Lại Mật Khẩu":
            if users_db:
                other_users = [u["username"] for u in users_db if u["username"] != current_username]
                if other_users:
                    target_pwd_user = st.selectbox("Chọn tài khoản cần cấp lại mật khẩu", other_users, key="sel_pwd_u")
                    with st.form("form_pwd"):
                        new_pwd = st.text_input("Mật khẩu mới (Bỏ trống để hệ thống tự tạo ngẫu nhiên)")
                        if st.form_submit_button("💾 Xác Nhận Cấp Lại", type="primary", use_container_width=True):
                            final_new_pwd = new_pwd if new_pwd.strip() else generate_strong_password()
                            is_valid, msg = validate_password_strength(final_new_pwd)
                            if not is_valid: show_popup_message("MẬT KHẨU YẾU", msg, "❌")
                            else:
                                conn = get_db_connection()
                                conn.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(final_new_pwd), target_pwd_user))
                                conn.commit()
                                conn.close()
                                show_popup_message("THÀNH CÔNG", f"Đã cập nhật mật khẩu cho **{target_pwd_user}**!\n\n🔑 **Mật khẩu mới là:** `{final_new_pwd}`", "✅")
                else: st.info("Không có tài khoản khác.")

        elif current_acc_menu == "🗑️ Xóa":
            if users_db:
                del_user = st.selectbox("Xóa tài khoản", [u["username"] for u in users_db], key="del_u")
                if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                    if del_user == st.session_state["username"]: show_popup_message("LỖI", "Không thể tự xóa bản thân!", icon="🚫")
                    else:
                        conn = get_db_connection()
                        conn.execute("DELETE FROM users WHERE username=?", (del_user,))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã xóa **{del_user}**!", icon="🗑️")

        elif current_acc_menu == "🛡️ Nhật Ký Bảo Mật":
            conn = get_db_connection()
            logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            if logs: st.dataframe(pd.DataFrame([{"ID": l["id"], "Thời gian": l["timestamp"], "Người dùng": l["username"], "Hành động": l["event_type"], "Trạng thái": l["status"]} for l in logs]), use_container_width=True)
            else: st.info("Chưa có bản ghi nhật ký nào.")
