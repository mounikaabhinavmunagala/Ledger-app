import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
from datetime import datetime
from PIL import Image
import io
import gspread
from google.oauth2.service_account import Credentials

# --- 1. APP CONFIG ---
st.set_page_config(page_title="Telugu Ledger Smart App", layout="wide")
st.title("📲 Telugu Ledger Smart App")

# --- 2. AUTHENTICATION (Service Account & Gemini) ---
@st.cache_resource
def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # Load secrets into a dictionary
        creds_info = {
            "type": st.secrets["connections"]["gsheets"]["type"],
            "project_id": st.secrets["connections"]["gsheets"]["project_id"],
            "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
            "private_key": st.secrets["connections"]["gsheets"]["private_key"],
            "client_email": st.secrets["connections"]["gsheets"]["client_email"],
            "client_id": st.secrets["connections"]["gsheets"]["client_id"],
            "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
            "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["connections"]["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["connections"]["gsheets"]["client_x509_cert_url"]
        }
        
        # FIX: Auto-clean the private key for "InvalidPadding" errors
        if "private_key" in creds_info:
            # Replace literal \n strings with real newlines
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Secret Loading Error: {e}")
        return None

# Initialize Connections
gc = get_gspread_client()
if gc:
    try:
        spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()
else:
    st.stop()

# --- 3. AI EXTRACTION LOGIC ---
def extract_ledger_data(img_file):
    # Using 1.5-flash for high-speed Telugu extraction
    model = genai.GenerativeModel('gemini-1.5-flash')
    img = Image.open(img_file)
    prompt = """
    Extract handwritten ledger data into a JSON list.
    Columns: Date, Place, Name, Item, Amount, Paid.
    - Transcribe Telugu names/items exactly.
    - If Date is empty, use current date.
    - Output ONLY valid JSON.
    """
    try:
        response = model.generate_content([prompt, img])
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Reading Error: {e}")
        return None

# --- 4. APP TABS ---
tab1, tab2 = st.tabs(["📤 Upload Ledger", "📥 Download Reports"])

with tab1:
    uploaded_files = st.file_uploader("Upload Ledger Photos", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
    if st.button("Process Photos"):
        all_new_entries = []
        for f in uploaded_files:
            with st.spinner(f"Reading {f.name}..."):
                items = extract_ledger_data(f)
                if items:
                    for i in items:
                        # Convert values to float and calculate balance
                        amt = float(str(i.get('Amount', 0)).replace(',', ''))
                        paid = float(str(i.get('Paid', 0)).replace(',', ''))
                        i['Amount'], i['Paid'] = amt, paid
                        i['Balance'] = amt - paid
                        all_new_entries.append(i)
        
        if all_new_entries:
            st.session_state.processed_data = all_new_entries
            st.success(f"Ready to save {len(all_new_entries)} transactions!")
        else:
            st.warning("No data found in the photos.")

    # Verification and Saving
    if "processed_data" in st.session_state:
        df_preview = pd.DataFrame(st.session_state.processed_data)
        st.write("### Verify Extracted Data:")
        st.dataframe(df_preview)
        
        if st.button("✅ SAVE PERMANENTLY TO GOOGLE SHEET"):
            try:
                # Append rows to the end of the sheet
                worksheet.append_rows(df_preview.values.tolist())
                st.success("🎉 Data successfully saved!")
                # Clear preview after saving
                del st.session_state.processed_data
            except Exception as e:
                st.error(f"Error while saving: {e}")

with tab2:
    try:
        records = worksheet.get_all_records()
        if records:
            master_df = pd.DataFrame(records)
            st.subheader("Generate Excel Reports")
            
            # --- Master Balance Sheet ---
            master_io = io.BytesIO()
            with pd.ExcelWriter(master_io, engine='openpyxl') as writer:
                for p in master_df['Place'].unique():
                    p_name = str(p) if p else "Unknown"
                    summary = master_df[master_df['Place'] == p].groupby('Name')['Balance'].sum().reset_index()
                    summary.to_excel(writer, sheet_name=p_name[:30], index=False)
            st.download_button("Download Master Balance Sheet", master_io.getvalue(), "Master_Report.xlsx")
            
            st.write("---")
            
            # --- Place-wise Detailed Sheet ---
            selected_place = st.selectbox("Select Place", master_df['Place'].unique())
            if st.button(f"Generate Workbook for {selected_place}"):
                place_df = master_df[master_df['Place'] == selected_place]
                place_io = io.BytesIO()
                with pd.ExcelWriter(place_io, engine='openpyxl') as writer:
                    for name in place_df['Name'].unique():
                        name_df = place_df[place_df['Name'] == name]
                        sh_name = str(name)[:30]
                        # Create individual account sheet
                        pd.DataFrame([["NAME:", name], ["TOTAL BALANCE:", name_df['Balance'].sum()]]).to_excel(writer, sheet_name=sh_name, index=False, header=False)
                        name_df.to_excel(writer, sheet_name=sh_name, index=False, startrow=3)
                st.download_button(f"Download {selected_place}_Ledger.xlsx", place_io.getvalue(), f"{selected_place}_Ledger.xlsx")
        else:
            st.info("Google Sheet is empty. Add data in the Upload tab.")
    except Exception as e:
        st.error(f"Report Error: {e}")
