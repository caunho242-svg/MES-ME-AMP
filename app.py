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

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(page_title="Dashboard OEE Toàn Diện (Secured & DB)", layout="wide", initial_sidebar_state="expanded")

ALL_FEATURES = ["🎛️ Dashboard OEE", "🏭 Quản Lý Máy Móc", "👤 Quản Lý Tài Khoản"]
ALL_MACHINE_EDIT_FIELDS = ["Tên máy", "Dây chuyền (Line)", "Đường dẫn máy", "File mẫu dữ liệu"]

# THÔNG SỐ BẢO MẬT
SESSION_TIMEOUT = 1800 # 30 phút
MAX_LOGIN_ATTEMPTS = 5 # Số lần thử tối đa
LOCKOUT_DURATION = 300 # Khóa 5 phút (300 giây)

# ==========================================
# 🗄️ KẾT NỐI CƠ SỞ DỮ LIỆU SQLITE
# ==========================================
def get_db_connection():
    conn = sqlite3.connect('mes_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# CÁC HÀM BẢO MẬT & MÃ HÓA
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

def log_security_event(username, event_type, status):
    conn = get_db_connection()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO audit_logs (timestamp, username, event_type, status) VALUES (?,?,?,?)", (timestamp, username, event_type, status))
    conn.commit()
    conn.close()

# ==========================================
# KHỞI TẠO BẢNG & DỮ LIỆU MẶC ĐỊNH
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Bảng Tài Khoản (Users)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    name TEXT,
                    department TEXT,
                    position TEXT,
                    role TEXT,
                    allowed_pages TEXT,
                    machine_perms TEXT,
                    editable_machine_fields TEXT
                )''')
    
    # 2. Bảng Máy Móc (Machines)
    c.execute('''CREATE TABLE IF NOT EXISTS machines (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    line TEXT,
                    url TEXT,
                    template_file TEXT,
                    has_file INTEGER
                )''')
    
    # 3. Bảng Nhật Ký Bảo Mật (Audit Logs)
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    username TEXT,
                    event_type TEXT,
                    status TEXT
                )''')

    # 4. Tạo tài khoản Admin & Manager mặc định
    c.execute("SELECT username FROM users WHERE username='admin'")
    if not c.fetchone():
        admin_pass = hash_password("Admin@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)''',
                  ('admin', admin_pass, 'Giám Đốc Nhà Máy', 'Ban Giám Đốc', 'Giám Đốc', 'Admin',
                   json.dumps(ALL_FEATURES), json.dumps(["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"]), json.dumps(ALL_MACHINE_EDIT_FIELDS)))
        
        manager_pass = hash_password("Manager@123")
        c.execute('''INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)''',
                  ('manager', manager_pass, 'Kỹ Sư IE', 'Kỹ Thuật (IE)', 'Trưởng Nhóm IE', 'Manager',
                   json.dumps(["🎛️ Dashboard OEE", "🏭 Quản Lý Máy Móc"]), json.dumps(["Xem", "Chỉnh sửa"]), json.dumps(["Đường dẫn máy"])))
    
    # 5. Dữ liệu máy móc mẫu
    c.execute("SELECT count(*) FROM machines")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M01", "Máy dập Block 1", "G103", "http://192.168.1.100/m01", "template_oee_g103.xlsx", 1))
        c.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", ("M02", "Máy Test Hipot", "G104", "http://192.168.1.101/m02", "template_oee_g104.csv", 1))
        
    conn.commit()
    conn.close()

# CHẠY KHỞI TẠO DB TẠI ĐÂY (Sẽ không còn lỗi NameError)
init_db()

# ==========================================
# CSS GIAO DIỆN NỔI BẬT
# ==========================================
st.markdown("""
    <style>
    @keyframes pulse-btn {
        0% { transform: scale(1); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4); }
        50% { transform: scale(1.02); box-shadow: 0 8px 20px rgba(245, 158, 11, 0.8); }
        100% { transform: scale(1); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4); }
    }
    div[key="btn_home_nav"] > button {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #ffffff !important; border: none !important; font-weight: 800 !important;
        font-size: 16px !important; border-radius: 10px !important; height: 48px !important;
        animation: pulse-btn 2s infinite !important; transition: all 0.3s ease !important;
        margin-bottom: 20px !important; border: 2px solid #fcd34d !important;
    }
    div[key="btn_home_nav"] > button:hover {
        background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
        animation: none !important; transform: translateY(-2px);
    }
    .login-header-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border: 1px solid #334155;
        border-radius: 16px; padding: 30px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); margin-bottom: 25px;
    }
    .login-title { color: #38bdf8; font-size: 2.2rem; font-weight: 800; margin-bottom: 8px; letter-spacing: 0.5px; }
    .login-subtitle { color: #94a3b8; font-size: 1rem; margin-bottom: 0; }
    .kpi-card-1 { background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 6px; }
    .kpi-card-2 { background-color: #f0fdf4; border-left: 5px solid #22c55e; padding: 15px; border-radius: 6px; }
    .kpi-card-3 { background-color: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 6px; }
    .kpi-card-4 { background-color: #fefce8; border-left: 5px solid #eab308; padding: 15px; border-radius: 6px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# CÁC HÀM HỖ TRỢ & MÔ PHỎNG DỮ LIỆU
# ==========================================
@st.dialog("🔔 THÔNG BÁO HỆ THỐNG")
def show_popup_message(title, message, icon="ℹ️"):
    st.markdown(f"### {icon} {title}")
    st.write(message)
    if st.button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

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
        data.append({
            "Ngày": d.strftime("%Y-%m-%d"), "Mã máy": machine_obj["id"], "Tên máy": machine_obj["name"],
            "Dây chuyền": machine_obj["line"], "Sẵn sàng (%)": round(availability, 1),
            "Hiệu suất (%)": round(performance, 1), "Chất lượng (%)": round(quality, 1),
            "OEE (%)": round(oee, 1), "Downtime (Phút)": round(np.random.uniform(10, 120), 1)
        })
    return pd.DataFrame(data)

def generate_mock_pareto_4m_data(machine_ids, start_date, end_date):
    seed_val = sum(ord(c) for m in machine_ids for c in m) + int(start_date.strftime("%d%m%Y"))
    np.random.seed(seed_val)
    stations = ["Block 1", "Block 2", "Block 3", "Block 4", "Block 5", "Block 6", "Chưa xác định"]
    downtimes = np.random.randint(200, 3000, size=len(stations))
    df_pareto = pd.DataFrame({"Trạm": stations, "So_Phut": downtimes}).sort_values(by="So_Phut", ascending=False).reset_index(drop=True)
    df_pareto["Phan_Tram_Tich_Luy"] = (df_pareto["So_Phut"].cumsum() / df_pareto["So_Phut"].sum()) * 100
    
    data_4m = {
        "labels": ['Máy móc (Machine)', 'Nguyên liệu (Material)', 'Phương pháp (Method)', 'Chưa phân loại'],
        "values": [int(np.random.uniform(500, 2000)), int(np.random.uniform(300, 1500)), int(np.random.uniform(100, 800)), int(np.random.uniform(100, 600))]
    }
    return df_pareto, data_4m

# ==========================================
# KHỞI TẠO TRẠNG THÁI SESSION
# ==========================================
if "LOGIN_ATTEMPTS" not in st.session_state: st.session_state["LOGIN_ATTEMPTS"] = {}
if "selected_menu" not in st.session_state: st.session_state["selected_menu"] = "🎛️ Dashboard OEE"

# ==========================================
# LOGIC ĐĂNG NHẬP / ĐĂNG XUẤT
# ==========================================
def login():
    _, col_center, _ = st.columns([1, 2.2, 1])
    with col_center:
        st.markdown("""
            <div class="login-header-card">
                <div style="font-size: 3rem; margin-bottom: 10px;">🏭</div>
                <div class="login-title">OEE MANAGEMENT SYSTEM</div>
                <div class="login-subtitle">Hệ Thống Giám Sát & Quản Lý Hiệu Suất Thiết Bị Smart Factory</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 Đăng Nhập Hệ Thống")
            with st.form("login_form"):
                username = st.text_input("👤 Tên đăng nhập", placeholder="Nhập tên đăng nhập")
                password = st.text_input("🔑 Mật khẩu", type="password", placeholder="Nhập mật khẩu")
                submit_button = st.form_submit_button("🚀 Đăng nhập", use_container_width=True, type="primary")
                
                if submit_button:
                    username_cleaned = username.strip().lower()
                    attempts_info = st.session_state["LOGIN_ATTEMPTS"].get(username_cleaned, {"count": 0, "lockout_until": 0})
                    
                    if time.time() < attempts_info["lockout_until"]:
                        st.error(f"❌ Tài khoản đang bị khóa. Thử lại sau {int(attempts_info['lockout_until'] - time.time())} giây!")
                        log_security_event(username_cleaned, "LOGIN_BLOCKED", "Thất bại (Locked)")
                    else:
                        conn = get_db_connection()
                        user = conn.execute("SELECT * FROM users WHERE username = ?", (username_cleaned,)).fetchone()
                        conn.close()

                        if user:
                            if verify_password(password, user['password_hash']):
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = {"count": 0, "lockout_until": 0}
                                st.session_state["logged_in"] = True
                                st.session_state["username"] = username_cleaned
                                st.session_state["user_info"] = {
                                    "name": user['name'], "department": user['department'], "position": user['position'],
                                    "role": user['role'], "allowed_pages": json.loads(user['allowed_pages']),
                                    "machine_perms": json.loads(user['machine_perms']), "editable_machine_fields": json.loads(user['editable_machine_fields'])
                                }
                                st.session_state["last_activity"] = time.time() 
                                log_security_event(username_cleaned, "LOGIN", "Thành công")
                                st.rerun()
                            else:
                                attempts_info["count"] += 1
                                if attempts_info["count"] >= MAX_LOGIN_ATTEMPTS:
                                    attempts_info["lockout_until"] = time.time() + LOCKOUT_DURATION
                                    st.error(f"❌ Nhập sai {MAX_LOGIN_ATTEMPTS} lần. Bị khóa 5 phút!")
                                    log_security_event(username_cleaned, "BRUTE_FORCE_DETECTED", "Khóa tài khoản")
                                else:
                                    st.error(f"❌ Sai mật khẩu! (Còn {MAX_LOGIN_ATTEMPTS - attempts_info['count']} lần thử)")
                                    log_security_event(username_cleaned, "LOGIN_FAILED", "Sai mật khẩu")
                                st.session_state["LOGIN_ATTEMPTS"][username_cleaned] = attempts_info
                        else:
                            st.error("❌ Tài khoản không tồn tại!")
                            log_security_event(username_cleaned, "LOGIN_FAILED", "User không tồn tại")

        st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.85rem; margin-top: 30px;'>© 2026 Smart Factory Management | Enterprise Secured (SQLite)</p>", unsafe_allow_html=True)

def logout(reason=""):
    log_security_event(st.session_state.get("username", "Unknown"), "LOGOUT", "Thành công")
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("user_info", None)
    st.session_state.pop("last_activity", None)
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    if reason: st.warning(reason)

def go_home():
    st.session_state["selected_menu"] = "🎛️ Dashboard OEE"
    st.session_state["menu_radio"] = "🎛️ Dashboard OEE"

# ==========================================
# GIAO DIỆN CHÍNH KHI ĐÃ ĐĂNG NHẬP
# ==========================================
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    if (time.time() - st.session_state.get("last_activity", 0)) > SESSION_TIMEOUT:
        logout("⏳ Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại!")
        st.rerun()
    else:
        st.session_state["last_activity"] = time.time() 

    current_user = st.session_state["user_info"]
    
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3652/3652191.png", width=95)
        st.success(f"👋 **{current_user['name']}**")
        st.info(f"📍 Bộ phận: **{current_user.get('department', 'N/A')}**\n\n💼 Chức vụ: **{current_user.get('position', 'N/A')}**\n\n🔑 Quyền: **{current_user.get('role', 'N/A')}**")
        st.markdown("---")
        
        user_pages = current_user.get("allowed_pages", ["🎛️ Dashboard OEE"])
        if "🎛️ Dashboard OEE" in user_pages:
            user_pages.remove("🎛️ Dashboard OEE")
            user_pages.insert(0, "🎛️ Dashboard OEE")

        selected_menu = st.radio("📌 ĐIỀU HƯỚNG HỆ THỐNG", user_pages, key="menu_radio")
        if selected_menu != st.session_state["selected_menu"]:
            st.session_state["selected_menu"] = selected_menu
            st.rerun()

        st.markdown("---")
        st.button("🚪 Đăng xuất an toàn", on_click=lambda: logout(), use_container_width=True)

    # LẤY DỮ LIỆU TỪ DATABASE
    conn = get_db_connection()
    machine_db_raw = conn.execute("SELECT * FROM machines").fetchall()
    machine_db = [{"id": m["id"], "name": m["name"], "line": m["line"], "url": m["url"], "template_file": m["template_file"], "has_file": bool(m["has_file"])} for m in machine_db_raw]
    conn.close()

    # ---------------------------------------------------------
    # TRANG 1: DASHBOARD OEE
    # ---------------------------------------------------------
    if selected_menu == "🎛️ Dashboard OEE":
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 22px; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 25px; border: 1px solid #334155;">
                <h1 style="margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: 1px; color: #38bdf8; text-transform: uppercase;">
                    🎛️ MANAGEMENT DASHBOARD V2 ACTIONABLE
                </h1>
            </div>
        """, unsafe_allow_html=True)

        st.subheader("🔍 Bộ Lọc Tìm Kiếm & Phân Tích Dữ Liệu")
        existing_lines = sorted(list(set([m["line"] for m in machine_db if m.get("line")])))
        
        c1, c2, c3, c4, c5 = st.columns([2.5, 2.5, 2.5, 2.5, 2])
        with c1: start_date = st.date_input("Từ ngày", date(2026, 8, 1))
        with c2: end_date = st.date_input("Đến ngày", date.today())
        with c3: selected_line = st.selectbox("Dây Chuyền", ["Tất cả Lines"] + existing_lines)
        with c4: selected_machine_str = st.selectbox("Máy", ["Tất cả Máy"] + [f"{m['id']} - {m['name']} (Line: {m['line']})" for m in machine_db])
        with c5:
            st.write("")
            st.write("")
            btn_search = st.button("🔎 Phân tích", use_container_width=True, type="primary")

        filtered_machines = machine_db.copy()
        if selected_line != "Tất cả Lines": filtered_machines = [m for m in filtered_machines if m["line"] == selected_line]
        if selected_machine_str != "Tất cả Máy": filtered_machines = [m for m in filtered_machines if m["id"] == selected_machine_str.split(" - ")[0]]

        target_display_name = selected_machine_str if selected_machine_str != "Tất cả Máy" else (selected_line if selected_line != "Tất cả Lines" else "Toàn Nhà Máy")

        if btn_search: show_popup_message("CẬP NHẬT DỮ LIỆU", f"Đã tải dữ liệu cho: **{target_display_name}**!", icon="📊")
        st.markdown("---")

        all_df_list = [generate_mock_machine_data(m, start_date, end_date) for m in filtered_machines]

        if all_df_list:
            df_filtered = pd.concat(all_df_list, ignore_index=True)
            avg_avail = df_filtered["Sẵn sàng (%)"].mean()
            
            st.markdown(f"### ⚙️ 01. Equipment Health Overview <span style='font-size: 1rem; font-weight: normal; color: #64748b;'>({target_display_name})</span>", unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            with k1: st.markdown(f'''<div class="kpi-card-1"><span style="color: #1e3a8a; font-size: 13px; font-weight: bold;">Downtime Rate</span><h2 style="color: #1d4ed8; margin: 5px 0 0 0;">{round(100 - avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k2: st.markdown(f'''<div class="kpi-card-2"><span style="color: #14532d; font-size: 13px; font-weight: bold;">Availability</span><h2 style="color: #15803d; margin: 5px 0 0 0;">{round(avg_avail, 1)}%</h2></div>''', unsafe_allow_html=True)
            with k3: st.markdown(f'''<div class="kpi-card-3"><span style="color: #7f1d1d; font-size: 13px; font-weight: bold;">MTBF (Ước tính)</span><h2 style="color: #b91c1c; margin: 5px 0 0 0;">{int(df_filtered["Downtime (Phút)"].mean() * 2)} Phút</h2></div>''', unsafe_allow_html=True)
            with k4: st.markdown(f'''<div class="kpi-card-4"><span style="color: #713f12; font-size: 13px; font-weight: bold;">MTTR (TB Sửa)</span><h2 style="color: #a16207; margin: 5px 0 0 0;">{round(df_filtered["Downtime (Phút)"].sum() / max(len(df_filtered), 1), 1)} Phút</h2></div>''', unsafe_allow_html=True)
            
            st.markdown("---")
            if current_user.get("role", "").lower() in ["manager", "admin"]:
                st.markdown(f"### 📊 02. Pareto Downtime (80/20) & Nguyên nhân 4M")
                df_pareto, data_4m = generate_mock_pareto_4m_data([m["id"] for m in filtered_machines], start_date, end_date)
                p_col, pie_col = st.columns([6, 4])
                with p_col:
                    fig_p = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_p.add_trace(go.Bar(x=df_pareto["Trạm"], y=df_pareto["So_Phut"], name="Downtime", marker_color="#e11d48"), secondary_y=False)
                    fig_p.add_trace(go.Scatter(x=df_pareto["Trạm"], y=df_pareto["Phan_Tram_Tich_Luy"], name="% Luỹ kế", mode="lines+markers+text", text=df_pareto["Phan_Tram_Tich_Luy"].round(0).astype(str)+"%", textposition="top left", marker=dict(color="#0f766e")), secondary_y=True)
                    st.plotly_chart(fig_p, use_container_width=True)
                    with st.expander("🖱️ Xem Bảng Dữ Liệu Pareto"): st.dataframe(df_pareto.style.format({"Phan_Tram_Tich_Luy": "{:.1f}%"}), use_container_width=True)
                with pie_col:
                    fig_pie = go.Figure(data=[go.Pie(labels=data_4m["labels"], values=data_4m["values"], hole=.4, marker=dict(colors=['#dc2626', '#ea580c', '#2563eb', '#94a3b8']))])
                    fig_pie.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.1))
                    st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("🔒 Hạn chế truy cập: Cần quyền Quản lý để xem biểu đồ chi tiết.")

            st.markdown("---")
            st.markdown("### 📈 03. Xu Hướng Chỉ Số OEE")
            c_chart, c_tbl = st.columns([6, 4])
            with c_chart:
                fig_l = go.Figure()
                for m_item in filtered_machines:
                    d_sub = df_filtered[df_filtered["Mã máy"] == m_item["id"]]
                    fig_l.add_trace(go.Scatter(x=d_sub["Ngày"], y=d_sub["OEE (%)"], mode='lines+markers', name=m_item['name']))
                st.plotly_chart(fig_l, use_container_width=True)
            with c_tbl:
                with st.expander("🖱️ Bảng Dữ Liệu Chi Tiết", expanded=True):
                    st.dataframe(df_filtered[["Ngày", "Mã máy", "Tên máy", "OEE (%)", "Downtime (Phút)"]], use_container_width=True, height=320)
        else:
            st.warning("⚠️ Không có dữ liệu phù hợp bộ lọc!")

    # ---------------------------------------------------------
    # TRANG 2: QUẢN LÝ MÁY MÓC
    # ---------------------------------------------------------
    elif selected_menu == "🏭 Quản Lý Máy Móc":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ THIẾT BỊ")
        st.markdown("---")
        u_perms = current_user.get("machine_perms", [])
        u_edits = current_user.get("editable_machine_fields", [])
        
        t_list, t_add, t_edit, t_del = st.tabs(["📋 Danh Sách Thiết Bị", "➕ Thêm Thiết Bị", "✏️ Chỉnh Sửa Máy", "🗑️ Xóa Máy"])

        with t_list:
            if "Xem" in u_perms:
                st.dataframe(pd.DataFrame(machine_db), use_container_width=True)
            else: st.error("🔒 Bạn không có quyền Xem danh sách.")

        with t_add:
            if "Thêm mới" in u_perms:
                with st.form("add_m_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        m_id = st.text_input("Mã máy*")
                        m_name = st.text_input("Tên máy*")
                        m_line = st.text_input("Dây chuyền*")
                    with c2:
                        m_url = st.text_input("Đường dẫn (URL)")
                        m_file = st.file_uploader("Nạp File Mẫu")
                    if st.form_submit_button("💾 Lưu Mới", use_container_width=True):
                        if not m_id or not m_name or not m_line: show_popup_message("LỖI", "Vui lòng nhập đủ thông tin có dấu *", "❌")
                        elif any(m["id"] == m_id for m in machine_db): show_popup_message("LỖI", "Mã máy đã tồn tại!", "⚠️")
                        else:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO machines VALUES (?,?,?,?,?,?)", (m_id, m_name, m_line, m_url, m_file.name if m_file else "", bool(m_file)))
                            conn.commit()
                            conn.close()
                            show_popup_message("THÀNH CÔNG", f"Đã thêm máy {m_name}!", "🎉")
            else: st.error("🔒 Không có quyền Thêm mới!")

        with t_edit:
            if "Chỉnh sửa" in u_perms and machine_db:
                sel_m = st.selectbox("Chọn máy cần sửa", [f"{m['id']} - {m['name']}" for m in machine_db]).split(" - ")[0]
                cur_m = next(m for m in machine_db if m["id"] == sel_m)
                st.info("💡 **Mã máy (ID)** là Khóa chính dùng để liên kết dữ liệu chạy máy và biểu đồ OEE nên không thể thay đổi. Nếu bạn nhập sai mã, vui lòng sang Tab 'Xóa' sau đó 'Thêm mới' thiết bị.")
                with st.form("edit_m_form"):
                    e_name = st.text_input("Tên máy", value=cur_m["name"], disabled="Tên máy" not in u_edits)
                    e_line = st.text_input("Dây chuyền", value=cur_m["line"], disabled="Dây chuyền (Line)" not in u_edits)
                    e_url = st.text_input("Đường dẫn", value=cur_m["url"], disabled="Đường dẫn máy" not in u_edits)
                    e_template_file = st.file_uploader("Thay File mẫu", disabled="File mẫu dữ liệu" not in u_edits)
                    
                    if st.form_submit_button("💾 Cập Nhật", use_container_width=True):
                        conn = get_db_connection()
                        conn.execute("UPDATE machines SET name=?, line=?, url=?, template_file=?, has_file=? WHERE id=?", 
                                     (e_name if "Tên máy" in u_edits else cur_m["name"],
                                      e_line if "Dây chuyền (Line)" in u_edits else cur_m["line"],
                                      e_url if "Đường dẫn máy" in u_edits else cur_m["url"],
                                      e_template_file.name if e_template_file else cur_m["template_file"],
                                      1 if e_template_file or cur_m["has_file"] else 0,
                                      sel_m))
                        conn.commit()
                        conn.close()
                        show_popup_message("THÀNH CÔNG", f"Đã cập nhật dữ liệu cho thiết bị **{sel_m}**!", "💾")

        with t_del:
            if "Xóa" in u_perms and machine_db:
                del_m = st.selectbox("Xóa máy", [f"{m['id']} - {m['name']}" for m in machine_db]).split(" - ")[0]
                if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM machines WHERE id=?", (del_m,))
                    conn.commit()
                    conn.close()
                    show_popup_message("ĐÃ XÓA", f"Đã xóa máy {del_m} khỏi hệ thống!", "🗑️")

    # ---------------------------------------------------------
    # TRANG 3: QUẢN LÝ TÀI KHOẢN (ĐÃ FIX QUYỀN ADMIN SỬA FULL)
    # ---------------------------------------------------------
    elif selected_menu == "👤 Quản Lý Tài Khoản":
        st.button("🏠 VỀ TRANG CHỦ DASHBOARD", on_click=go_home, use_container_width=True, key="btn_home_nav")
        st.markdown("## ⚙️ QUẢN TRỊ HỆ THỐNG - QUẢN LÝ TÀI KHOẢN")
        st.markdown("---")
        
        conn = get_db_connection()
        users_db = conn.execute("SELECT * FROM users").fetchall()
        conn.close()

        t_lst, t_add_u, t_edit_u, t_del_u, t_logs = st.tabs(["📋 Danh Sách", "➕ Tạo Mới", "✏️ Sửa Thông Tin", "🗑️ Xóa", "🛡️ Audit Logs"])

        with t_lst:
            st.dataframe(pd.DataFrame([{"Tài khoản": u["username"], "Họ Tên": u["name"], "Bộ phận": u["department"], "Chức vụ": u["position"], "Quyền": u["role"]} for u in users_db]), use_container_width=True)

        with t_add_u:
            with st.form("add_user_form"):
                st.info("🔐 Mật khẩu ≥ 8 ký tự (Gồm: HOA, thường, số, ký tự đặc biệt)")
                c1, c2 = st.columns(2)
                with c1:
                    a_user = st.text_input("Tên tài khoản*")
                    a_pass = st.text_input("Mật khẩu*", type="password")
                    a_name = st.text_input("Họ và Tên")
                with c2:
                    a_dept = st.text_input("Bộ phận", value="Sản Xuất")
                    a_pos = st.text_input("Chức vụ", value="Nhân Viên")
                    a_role = st.text_input("Quyền*", value="Operator")

                a_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=["🎛️ Dashboard OEE"])
                a_m_perms = st.multiselect("Quyền thiết bị", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=["Xem"])
                a_edits = st.multiselect("Cột được sửa", ALL_MACHINE_EDIT_FIELDS, default=["Đường dẫn máy"])

                if st.form_submit_button("➕ Tạo Mới", use_container_width=True):
                    if not validate_username(a_user): show_popup_message("LỖI", "Tên đăng nhập 3-20 ký tự (Không chứa dấu)!", "❌")
                    else:
                        valid, msg = validate_password_strength(a_pass)
                        if not valid: show_popup_message("MẬT KHẨU YẾU", msg, "❌")
                        elif any(u["username"] == a_user.lower() for u in users_db): show_popup_message("LỖI", "Tài khoản đã tồn tại!", "⚠️")
                        else:
                            conn = get_db_connection()
                            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)", 
                                        (a_user.lower(), hash_password(a_pass), a_name, a_dept, a_pos, a_role, json.dumps(a_pages), json.dumps(a_m_perms), json.dumps(a_edits)))
                            conn.commit()
                            conn.close()
                            log_security_event(st.session_state["username"], f"TẠO USER ({a_user})", "Thành công")
                            show_popup_message("THÀNH CÔNG", f"Đã tạo tài khoản {a_user}!", "👤")

        with t_edit_u:
            sel_u = st.selectbox("Chọn tài khoản cần sửa", [u["username"] for u in users_db])
            cur_u = next(u for u in users_db if u["username"] == sel_u)
            
            with st.form("edit_user_form"):
                st.markdown("**1. Thông tin cơ bản:**")
                e_pass = st.text_input("Mật khẩu mới (Để trống nếu không đổi)", type="password")
                e_name = st.text_input("Họ và Tên", value=cur_u["name"])
                
                c1, c2, c3 = st.columns(3)
                with c1: e_dept = st.text_input("Bộ phận", value=cur_u["department"])
                with c2: e_pos = st.text_input("Chức vụ", value=cur_u["position"])
                with c3: e_role = st.text_input("Quyền (Role)", value=cur_u["role"])

                st.markdown("**2. Phân quyền truy cập & Thao tác:**")
                e_pages = st.multiselect("Trang truy cập", ALL_FEATURES, default=json.loads(cur_u["allowed_pages"]))
                e_m_perms = st.multiselect("Quyền thiết bị", ["Xem", "Thêm mới", "Chỉnh sửa", "Xóa"], default=json.loads(cur_u["machine_perms"]))
                e_edits = st.multiselect("Cột được sửa", ALL_MACHINE_EDIT_FIELDS, default=json.loads(cur_u["editable_machine_fields"]))
                
                if st.form_submit_button("💾 Lưu Thay Đổi Toàn Diện", use_container_width=True):
                    if e_pass:
                        valid, msg = validate_password_strength(e_pass)
                        if not valid: 
                            show_popup_message("LỖI", msg, "❌")
                            st.stop()
                    
                    conn = get_db_connection()
                    conn.execute("""UPDATE users 
                                    SET password_hash=?, name=?, department=?, position=?, role=?, 
                                        allowed_pages=?, machine_perms=?, editable_machine_fields=? 
                                    WHERE username=?""", 
                                 (hash_password(e_pass) if e_pass else cur_u["password_hash"], 
                                  e_name, e_dept, e_pos, e_role, 
                                  json.dumps(e_pages), json.dumps(e_m_perms), json.dumps(e_edits), 
                                  sel_u))
                    conn.commit()
                    conn.close()
                    
                    # Cập nhật lại session nếu người dùng đang tự sửa quyền của chính mình
                    if sel_u == st.session_state["username"]:
                        st.session_state["user_info"].update({
                            "name": e_name, "department": e_dept, "position": e_pos, "role": e_role,
                            "allowed_pages": e_pages, "machine_perms": e_m_perms, "editable_machine_fields": e_edits
                        })
                    
                    log_security_event(st.session_state["username"], f"SỬA USER TOÀN DIỆN ({sel_u})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã cập nhật toàn bộ thông tin cho {sel_u}!", "💾")

        with t_del_u:
            del_u = st.selectbox("Xóa tài khoản", [u["username"] for u in users_db], key="del_u")
            if st.button("🗑️ Xác Nhận Xóa", type="primary", use_container_width=True):
                if del_u == st.session_state["username"]: show_popup_message("LỖI", "Không thể tự xóa bản thân!", "🚫")
                else:
                    conn = get_db_connection()
                    conn.execute("DELETE FROM users WHERE username=?", (del_u,))
                    conn.commit()
                    conn.close()
                    log_security_event(st.session_state["username"], f"XÓA USER ({del_u})", "Thành công")
                    show_popup_message("THÀNH CÔNG", f"Đã xóa {del_u}!", "🗑️")

        with t_logs:
            st.subheader("🛡️ Lịch Sử Bảo Mật Hệ Thống")
            conn = get_db_connection()
            logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            if logs:
                st.dataframe(pd.DataFrame([{"ID": l["id"], "Thời gian": l["timestamp"], "Người dùng": l["username"], "Hành động": l["event_type"], "Trạng thái": l["status"]} for l in logs]), use_container_width=True)
            else: st.info("Chưa có ghi nhận nào.")
