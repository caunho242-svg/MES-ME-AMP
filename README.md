# MES-ME-AMP
import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

# -------------------------------------------------------------------
# 1. CẤU HÌNH TÀI KHOẢN ĐĂNG NHẬP (USER & PASSWORD)
# -------------------------------------------------------------------
# Mật khẩu đã được mã hóa sẵn (Ví dụ: pass123 -> $2b$12...)
credentials = {
    'usernames': {
        'admin': {
            'name': 'Quản trị viên',
            'password': '$2b$12$eImiTXuWVxfM37uY4JANjOL.sUTih78Y90YKh.I/s4R0pM5WJ164a'  # Pass: admin123
        },
        'nhanvien1': {
            'name': 'Thành viên A',
            'password': '$2b$12$6/S1QO4oG4D3kC4Zk6.xVuN8Xj0S6Z/3A.g/eR4T5e/6G3H1J2K3L'  # Pass: user123
        }
    }
}

# Tạo mô-đun đăng nhập
authenticator = stauth.Authenticate(
    credentials,
    'excel_ai_cookie',
    'auth_key_123456',
    cookie_expiry_days=1
)

# -------------------------------------------------------------------
# 2. XỬ LÝ GIAO DIỆN ĐĂNG NHẬP
# -------------------------------------------------------------------
st.set_page_config(page_title="Hệ thống Trợ lý AI Excel", layout="wide")

name, authentication_status, username = authenticator.login('Đăng nhập hệ thống', 'main')

if authentication_status == False:
    st.error('Tài khoản hoặc mật khẩu không chính xác!')
elif authentication_status == None:
    st.warning('Vui lòng nhập Nickname và Mật khẩu để tiếp tục.')
elif authentication_status:
    # -------------------------------------------------------------------
    # 3. GIAO DIỆN CHÍNH SAU KHI ĐĂNG NHẬP THÀNH CÔNG
    # -------------------------------------------------------------------
    authenticator.logout('Đăng xuất', 'sidebar')
    st.title(f"🤖 Trợ lý AI Truy xuất Excel - Xin chào {name}!")
    st.markdown("---")

    # Cấu hình API Key trong Sidebar
    with st.sidebar:
        st.header("⚙️ Cấu hình API")
        openai_api_key = st.text_input("Nhập OpenAI API Key:", type="password")
        st.info("Nhập API Key của OpenAI để kích hoạt trí tuệ nhân tạo.")

    # Tải lên file Excel
    uploaded_file = st.file_uploader("📂 Chọn file Excel để truy xuất dữ liệu", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        # Đọc dữ liệu Excel bằng Pandas
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            st.subheader("📊 Xem trước dữ liệu:")
            st.dataframe(df.head(5))

            # Ô nhập câu hỏi cho AI
            st.markdown("---")
            query = st.text_input("💬 Nhập câu hỏi/yêu cầu truy xuất dữ liệu từ file Excel:")

            if query:
                if not openai_api_key:
                    st.error("⚠️ Vui lòng nhập OpenAI API Key ở thanh bên trái để tiếp tục!")
                else:
                    with st.spinner("AI đang tính toán và truy xuất dữ liệu..."):
                        try:
                            # Khởi tạo mô hình AI
                            llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", api_key=openai_api_key)
                            
                            # Tạo Agent đọc bảng Pandas
                            agent = create_pandas_dataframe_agent(
                                llm, 
                                df, 
                                verbose=True, 
                                allow_dangerous_code=True
                            )
                            
                            # AI thực thi truy vấn
                            response = agent.run(query)
                            st.success("✅ Kết quả:")
                            st.write(response)
                        except Exception as e:
                            st.error(f"Xảy ra lỗi trong quá trình xử lý: {e}")

        except Exception as e:
            st.error(f"Lỗi đọc file Excel: {e}")
