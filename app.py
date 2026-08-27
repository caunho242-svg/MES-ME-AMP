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
import streamlit.components.v1 as components

try:
    from PIL import Image
except ImportError:
    pass

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(
    page_title="ME-AMP | Factory Management",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        body {{ font-family: 'Arial', sans-serif; padding: 20px; }}
        h2 {{ text-align: center; color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 14px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f4f4f4; color: #333; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
    </style>
    </head>
    <body onload="window.print()">
    <h2>{title} ({date.today().strftime('%d/%m/%Y')})</h2>
    {df.to_html(index=False)}
    <p style="text-align: right; margin-top: 20px; font-style: italic;">Phần mềm quản lý ME-AMP</p>
    </body>
    </html>
    """
    return base64.b64encode(html.encode('utf-8-sig')).decode()

# ==========================================
# KHỞI TẠO BẢNG & DỮ LIỆU
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT, name TEXT, department TEXT, position TEXT, role TEXT, allowed_pages TEXT, machine_perms TEXT, editable_machine_fields TEXT, spare_perms TEXT)''')
    try: c.execute("ALTER TABLE users ADD COLUMN spare_perms TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE users ADD COLUMN last_active REAL")
    except sqlite3.OperationalError: pass
    c.execute('''CREATE TABLE IF NOT EXISTS machines (id TEXT PRIMARY KEY, name TEXT, line TEXT, url TEXT, template_file TEXT, has_file INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS spare_parts (part_id TEXT PRIMARY KEY, part_name TEXT, category TEXT, model_applicable TEXT, location TEXT, quantity INTEGER, min_quantity INTEGER, unit TEXT, image_url TEXT)''')
    try: c.execute("ALTER TABLE spare_parts ADD COLUMN image_url TEXT")
    except sqlite3.OperationalError: pass
    c.execute('''CREATE TABLE IF NOT EXISTS spare_part_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, part_id TEXT, action_type TEXT, quantity_changed INTEGER, remaining_qty INTEGER, user_action TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS spare_request_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, part_id TEXT, part_name TEXT, quantity_requested INTEGER, requester TEXT, line_working TEXT, notes TEXT, status TEXT)''')
    try: c.execute("ALTER TABLE spare_request_queue ADD COLUMN line_working TEXT")
    except sqlite3.OperationalError: pass
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
# CSS GIAO DIỆN CÔNG NGHỆ CAO & FONT RÕ NÉT
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Orbitron:wght@500;700;900&display=swap');
    
    /* Global Font & Theme */
    .stApp { background-color: #050b14; color: #f8fafc; font-family: 'Inter', sans-serif; }
    
    /* Headings */
    h1, h2, h3, h4 { color: #00f2fe !important; text-shadow: 0 0 12px rgba(0, 242, 254, 0.4); font-family: 'Orbitron', sans-serif; letter-spacing: 0.5px; }
    
    /* Make Alerts & Toasts Stand Out */
    div[data-testid="stToast"] { background: rgba(2, 6, 23, 0.95) !important; border: 2px solid #00f2fe !important; box-shadow: 0 8px 30px rgba(0, 242, 254, 0.5) !important; border-radius: 10px !important; z-index: 99999 !important; }
    div[data-testid="stToast"] * { color: #ffffff !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }
    .stAlert { font-weight: 600; border-width: 1px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); font-family: 'Inter', sans-serif; }
    
    /* Inputs */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div { background-color: #0f172a !important; color: #38bdf8 !important; border: 1px solid #1e293b !important; border-radius: 8px; font-family: 'Inter', sans-serif; font-weight: 500; }
    .stTextInput>div>div>input:focus, .stSelectbox>div>div>div:focus { border-color: #00f2fe !important; box-shadow: 0 0 8px rgba(0,242,254,0.3) !important; }
    
    /* Buttons */
    .stButton>button { background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%) !important; color: #000 !important; border: none !important; font-weight: 700 !important; border-radius: 8px !important; box-shadow: 0 0 15px rgba(0, 242, 254, 0.4) !important; transition: all 0.3s ease !important; font-family: 'Inter', sans-serif; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0, 242, 254, 0.7) !important; }
    
    /* Cards */
    .login-header-card, div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlockBorderWrapper"] { background: rgba(15, 23, 42, 0.7) !important; border: 1px solid #1e293b !important; border-radius: 12px !important; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important; backdrop-filter: blur(10px); }
    
    /* Online Bar */
    .online-bar { background: linear-gradient(90deg, #064e3b 0%, #022c22 100%); padding: 12px 18px; border-radius: 8px; border: 1px solid #10b981; margin-bottom: 20px; color: #a7f3d0; font-family: 'Inter', sans-serif; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); display: flex; align-items: center; gap: 10px; z-index: 100; position: relative; }
    
    @media print {
        [data-testid="stSidebar"], button, .online-bar, div.stRadio, header { display: none !important; }
        .stApp { background: white !important; color: black !important; }
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
            <div class="login-header-card">
                <div style="font-size: 4rem; margin-bottom: 5px; text-shadow: 0 0 20px #00f2fe;">🌐</div>
                <div style="color: #00f2fe; font-size: 2.8rem; font-weight: 900; margin-bottom: 8px; letter-spacing: 2px; font-family: 'Orbitron', sans-serif;">ME-AMP</div>
                <div style="color: #38bdf8; font-size: 1.1rem; font-weight: 500; font-family: 'Inter', sans-serif;">HỆ THỐNG QUẢN LÝ CÔNG NGHỆ CAO</div>
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
                                "machine_perms": json.loads(user['machine_perms']), "spare_perms": json.loads(user['spare_perms']) if user['spare_perms'] else ["Xem", "Giao dịch"]
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
        st.markdown("<p style='text-align: center; color: #475569; font-size: 0.85rem; margin-top: 30px;'>© 2026 ME-AMP Core System | AI-Powered Enterprise</p>", unsafe_allow_html=True)

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
        st.markdown("<h2 style='text-align: center; color: #00f2fe; text-shadow: 0 0 10px #00f2fe;'>ME-AMP</h2>", unsafe_allow_html=True)
        st.success(f"👋 **{current_user['name']}**")
        st.info(f"📍 Bộ phận: **{current_user.get('department', 'N/A')}**\n\n💼 Chức vụ: **{current_user.get('position', 'N/A')}**\n\n🔑 Quyền: **{current_user.get('role', 'N/A')}**")
        
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
    # THANH HIỂN THỊ NGƯỜI DÙNG ONLINE TOÀN CỤC (HIỂN THỊ TRÊN MỌI TAB)
    # =========================================================================
    conn = get_db_connection()
    online_users_db = conn.execute("SELECT name, department FROM users WHERE last_active >= ?", (time.time() - 300,)).fetchall()
    machine_db_raw = conn.execute("SELECT * FROM machines").fetchall()
    machine_db = [{"id": m["id"], "name": m["name"], "line": m["line"]} for m in machine_db_raw]
    conn.close()
    
    if online_users_db:
        online_names = [f"🟢 <b>{u['name']}</b> ({u['department']})" for u in online_users_db]
        st.markdown(f"""
            <div class='online-bar'>
                <span style="font-size: 20px;">👥</span> 
                <span><b style="color: #fff;">Hệ thống ME-AMP đang trực tuyến ({len(online_users_db)}):</b> {' &nbsp;&nbsp;|&nbsp;&nbsp; '.join(online_names)}</span>
            </div>
        """, unsafe_allow_html=True)

    # =========================================================================
    # TRANG 1: DASHBOARD OEE
    # =========================================================================
    if selected_menu == "🎛️ Dashboard OEE":
        st.markdown("""<div style="background: rgba(15,23,42,0.6); padding: 22px; border-radius: 12px; text-align: center; border: 1px solid #00f2fe; margin-bottom: 15px;">
                        <h1 style="margin: 0; font-size: 2.2rem; font-weight: 900; letter-spacing: 2px;">🎛️ QUẢN TRỊ HIỆU SUẤT TỔNG THỂ (OEE)</h1>
                    </div>""", unsafe_allow_html=True)

        st.info("Biểu đồ và số liệu hệ thống đang được tải (Demo)...")

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

        # MENU LUÂN CHUYỂN
        sp_menu_options = []
        if "Xem" in user_spare_perms: sp_menu_options.extend(["🔍 Tra Cứu", "📝 Yêu Cầu Của Tôi"])
        if "Giao dịch" in user_spare_perms: sp_menu_options.append("📥 Xuất / Nhập")
        if "Phê duyệt" in user_spare_perms or current_user.get("role") == "Admin": sp_menu_options.append("✅ Phê Duyệt")
        if "Thêm mới" in user_spare_perms: sp_menu_options.append("➕ Thêm Mới")
        if "Xem" in user_spare_perms: sp_menu_options.append("📜 Lịch Sử")

        if not sp_menu_options:
            st.error("🔒 Bạn không có quyền truy cập Kho Spare Part.")
        else:
            current_sp_menu = st.radio("📍 Bảng Điều Khiển:", sp_menu_options, horizontal=True)
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

                # Lọc dữ liệu
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

                # Tùy chọn xem
                st.write("")
                view_mode = st.radio("Chế độ hiển thị:", ["🗂️ Dạng Lưới", "📄 Dạng Bảng"], horizontal=True)

                # ==============================
                # CHẾ ĐỘ DẠNG BẢNG (KÈM IN ẤN & SỬA)
                # ==============================
                if view_mode == "📄 Dạng Bảng":
                    st.caption(f"Tìm thấy **{len(filtered_sp)}** vật tư.")
                    
                    df_export = pd.DataFrame(filtered_sp)[['part_id', 'part_name', 'category', 'model_applicable', 'location', 'quantity', 'unit']] if filtered_sp else pd.DataFrame()
                    if not df_export.empty:
                        df_export.columns = ["Mã Vật Tư", "Tên Vật Tư", "Nhóm", "Dùng Cho Máy", "Vị Trí Kệ", "Tồn Kho", "Đơn Vị Tính"]
                        
                        # CÁC NÚT XUẤT VÀ IN ẤN
                        btn_col1, btn_col2, btn_col3, _ = st.columns([2, 2, 2.5, 4])
                        # 1. Xuất Excel (Đã Lọc)
                        csv_filtered = df_export.to_csv(index=False).encode('utf-8-sig')
                        btn_col1.download_button("📥 Xuất Excel (Đã Lọc)", data=csv_filtered, file_name=f"VatTu_Loc_{date.today()}.csv", mime="text/csv", use_container_width=True)
                        
                        # 2. Xuất Excel (Tất Cả Kho)
                        df_all = pd.DataFrame(sp_data)[['part_id', 'part_name', 'category', 'model_applicable', 'location', 'quantity', 'unit']]
                        df_all.columns = ["Mã Vật Tư", "Tên Vật Tư", "Nhóm", "Dùng Cho Máy", "Vị Trí Kệ", "Tồn Kho", "Đơn Vị Tính"]
                        csv_all = df_all.to_csv(index=False).encode('utf-8-sig')
                        btn_col2.download_button("📥 Xuất Excel (Tất Cả)", data=csv_all, file_name=f"Kho_Tong_{date.today()}.csv", mime="text/csv", use_container_width=True)
                        
                        # 3. Xuất PDF / In Ấn (Chỉ Lấy Bảng Đã Lọc)
                        b64_html = generate_printable_html(df_export, "DANH SÁCH VẬT TƯ (ĐÃ LỌC)")
                        print_href = f'<a href="data:text/html;base64,{b64_html}" target="_blank" style="display: block; text-align: center; background: linear-gradient(90deg, #ef4444 0%, #f43f5e 100%); color: white; padding: 7px; border-radius: 6px; text-decoration: none; font-weight: bold; height: 38px;">🖨️ In PDF / Giấy (Đã Lọc)</a>'
                        with btn_col3:
                            st.markdown(print_href, unsafe_allow_html=True)

                        st.dataframe(df_export, use_container_width=True)

                        # TÍNH NĂNG CHỈNH SỬA CHO DẠNG BẢNG (Chọn dòng để sửa)
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
                                        conn.commit()
                                        conn.close()
                                        st.toast("✅ Cập nhật thành công!", icon="💾")
                                        time.sleep(0.5)
                                        st.rerun()

                # ==============================
                # CHẾ ĐỘ DẠNG LƯỚI
                # ==============================
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

                                    # CHỈNH SỬA DẠNG LƯỚI (Nằm dưới cùng thẻ vật tư)
                                    if "Chỉnh sửa" in user_spare_perms:
                                        with st.popover(f"✏️ Sửa nhanh", use_container_width=True):
                                            with st.form(f"qe_{item['part_id']}"):
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
                                                
                                                if st.form_submit_button("💾 Lưu Sửa", use_container_width=True, type="primary"):
                                                    img_db = image_to_base64(q_img) if q_img else item.get("image_url")
                                                    conn = get_db_connection()
                                                    conn.execute("UPDATE spare_parts SET part_name=?, category=?, model_applicable=?, location=?, min_quantity=?, unit=?, image_url=? WHERE part_id=?", (q_name, q_cat, q_model, q_loc, q_min, q_unit, img_db, item['part_id']))
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
            # 5. THÊM MỚI
            # ----------------------------------------
            elif current_sp_menu == "➕ Thêm Mới":
                with st.container(border=True):
                    st.subheader("➕ Tạo Mã Phụ Tùng Mới")
                    n_id = st.text_input("Mã phụ tùng*")
                    n_name = st.text_input("Tên phụ tùng*")
                    c_n1, c_n2 = st.columns(2)
                    with c_n1: n_cat = st.text_input("Nhóm", value="Cơ khí")
                    with c_n2: n_mod = st.text_input("Máy áp dụng", value="Tất cả")
                    c_n3, c_n4, c_n5 = st.columns(3)
                    with c_n3: n_loc = st.text_input("Vị trí kệ", value="Kệ A")
                    with c_n4: n_qty = st.number_input("Tồn ban đầu", min_value=0, value=10)
                    with c_n5: n_min = st.number_input("Tồn tối thiểu", min_value=1, value=5)
                    n_unit = st.text_input("ĐVT", value="Cái")
                    st.markdown("**📸 Hình ảnh vật tư:**")
                    img_method_add = st.radio("Cách thêm ảnh:", ["📂 Tải ảnh lên", "📷 Chụp trực tiếp"], horizontal=True)
                    n_file = st.file_uploader("Chọn file ảnh", type=["png","jpg","jpeg"]) if img_method_add == "📂 Tải ảnh lên" else st.camera_input("Chụp ảnh trực tiếp")
                    if st.button("💾 Lưu Mã Phụ Tùng Mới", type="primary", use_container_width=True):
                        if not n_id or not n_name: show_popup_message("LỖI", "Nhập đủ Mã và Tên!", "❌")
                        else:
                            img_save = image_to_base64(n_file) if n_file else "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&q=80"
                            conn = get_db_connection()
                            conn.execute("INSERT INTO spare_parts VALUES (?,?,?,?,?,?,?,?,?)", (n_id, n_name, n_cat, n_mod, n_loc, n_qty, n_min, n_unit, img_save))
                            conn.commit()
                            conn.close()
                            show_popup_message("THÀNH CÔNG", f"Đã thêm {n_name}!", "🎉")

            # ----------------------------------------
            # 6. LỊCH SỬ
            # ----------------------------------------
            elif current_sp_menu == "📜 Lịch Sử":
                conn = get_db_connection()
                logs = conn.execute("SELECT * FROM spare_part_logs ORDER BY id DESC LIMIT 100").fetchall()
                conn.close()
                if logs: 
                    exp_c1, exp_c2, _ = st.columns([2, 2, 6])
                    df_log = pd.DataFrame([dict(l) for l in logs])
                    df_log.columns = ["ID", "Thời Gian", "Mã VT", "Thao Tác", "SL Thay Đổi", "Tồn Mới", "Người Thực Hiện", "Ghi Chú"]
                    csv_data = df_log.to_csv(index=False).encode('utf-8-sig')
                    exp_c1.download_button("📥 Xuất Lịch Sử (CSV)", data=csv_data, file_name=f"LichSuGiaoDich_{date.today()}.csv", mime="text/csv", use_container_width=True)
                    
                    b64_html = generate_printable_html(df_log, "LỊCH SỬ GIAO DỊCH KHO")
                    print_href = f'<a href="data:text/html;base64,{b64_html}" target="_blank" style="display: block; text-align: center; background: linear-gradient(90deg, #ef4444 0%, #f43f5e 100%); color: white; padding: 7px; border-radius: 6px; text-decoration: none; font-weight: bold; height: 38px;">🖨️ In Lịch Sử (PDF)</a>'
                    with exp_c2:
                        st.markdown(print_href, unsafe_allow_html=True)
                    st.dataframe(df_log, use_container_width=True)
                else: st.info("Chưa có lịch sử.")

    # =========================================================================
    # TRANG 3: QUẢN LÝ TÀI KHOẢN (Các tab khác giữ nguyên nhưng đổi Title)
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

        tab_list, tab_add, tab_edit, tab_pwd, tab_delete, tab_logs = st.tabs([
            "📋 Danh Sách Tài Khoản", "➕ Tạo Mới", "✏️ Chỉnh Sửa", "🔑 Cấp Lại Mật Khẩu", "🗑️ Xóa", "🛡️ Nhật Ký Bảo Mật"
        ])

        with tab_list:
            display_data = []
            for u in users_db:
                pages_list = json.loads(u["allowed_pages"]) if u["allowed_pages"] else []
                display_data.append({
                    "Tài khoản": u["username"], "Họ và Tên": u["name"],
                    "Bộ phận": u["department"], "Chức vụ": u["position"],
                    "Quyền (Role)": u["role"], "Các mục truy cập": ", ".join(pages_list)
                })
            st.dataframe(pd.DataFrame(display_data), use_container_width=True)

        with tab_add:
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

        with tab_edit:
            if users_db:
                target_user = st.selectbox("Chọn tài khoản cần sửa", [u["username"] for u in users_db], key="sel_edit_u")
                cur_u = next(u for u in users_db if u["username"] == target_user)
                disable_perms = (target_user == current_username and current_username.lower() != "admin")

                with st.form("form_edit_user"):
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

        with tab_pwd:
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

        with tab_delete:
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

        with tab_logs:
            conn = get_db_connection()
            logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            if logs: st.dataframe(pd.DataFrame([{"ID": l["id"], "Thời gian": l["timestamp"], "Người dùng": l["username"], "Hành động": l["event_type"], "Trạng thái": l["status"]} for l in logs]), use_container_width=True)
