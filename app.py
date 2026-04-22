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
    # Scopes for Google Sheets and Drive
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Get credentials from Streamlit Secrets
    creds_info = st.secrets["connections"]["gsheets"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

try:
    # Initialize Google Sheets connection
    gc = get_gspread_client()
    spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    sh = gc.open_by_url(spreadsheet_url)
    worksheet = sh.get_worksheet(0) # Assumes data is in the first tab (Sheet1)
    
    # Initialize Gemini
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

# --- 3. AI EXTRACTION LOGIC ---
def extract_ledger_data(img_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    img = Image.open(img_file)
    prompt = """
    Extract handwritten ledger data into a JSON list.
    Columns: Date, Place, Name, Item, Amount, Paid.
    - If Date is missing, use today's date.
    - Transcribe Telugu names/items exactly.
    - Output ONLY valid JSON.
    """
    try:
        response = model.generate_content([prompt, img])
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Error: {e}")
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
                        # Clean numbers and calculate balance
                        amt = float(str(i.get('Amount', 0)).replace(',', ''))
                        paid = float(str(i.get('Paid', 0)).replace(',', ''))
                        i['Amount'], i['Paid'] = amt, paid
                        i['Balance'] = amt - paid
                        all_new_entries.append(i)
        
        if all_new_entries:
            st.session_state.processed_data = all_new_entries
            st.success(f"Found {len(all_new_entries)} transactions!")
        else:
            st.warning("No data found in the uploaded images.")

    # Show table and Save button if data is processed
    if "processed_data" in st.session_state:
        df_preview = pd.DataFrame(st.session_state.processed_data)
        st.write("### Preview of Data:")
        st.dataframe(df_preview)
        
        if st.button("✅ SAVE ALL TO GOOGLE SHEET"):
            try:
                # Convert list of dicts to list of lists for gspread
                rows_to_append = df_preview.values.tolist()
                worksheet.append_rows(rows_to_append)
                st.success("🎉 Data successfully saved to your Google Sheet!")
                # Clear state so it doesn't double-save
                del st.session_state.processed_data
            except Exception as e:
                st.error(f"Saving Error: {e}")

with tab2:
    try:
        # Fetch latest data from sheet
        records = worksheet.get_all_records()
        if records:
            master_df = pd.DataFrame(records)
            st.subheader("Generate Excel Reports")
            
            # --- Master Download ---
            master_io = io.BytesIO()
            with pd.ExcelWriter(master_io, engine='openpyxl') as writer:
                for p in master_df['Place'].unique():
                    p_name = str(p) if p else "Unknown"
                    summary = master_df[master_df['Place'] == p].groupby('Name')['Balance'].sum().reset_index()
                    summary.to_excel(writer, sheet_name=p_name[:30], index=False)
            st.download_button("Download Master Balances", master_io.getvalue(), "Master_Ledger.xlsx")
            
            st.write("---")
            
            # --- Place-wise Detailed Download ---
            selected_place = st.selectbox("Select Place", master_df['Place'].unique())
            if st.button(f"Generate {selected_place} Details"):
                place_df = master_df[master_df['Place'] == selected_place]
                place_io = io.BytesIO()
                with pd.ExcelWriter(place_io, engine='openpyxl') as writer:
                    for name in place_df['Name'].unique():
                        name_df = place_df[place_df['Name'] == name]
                        sheet_name = str(name)[:30]
                        # Header
                        pd.DataFrame([["NAME:", name], ["TOTAL:", name_df['Balance'].sum()]]).to_excel(writer, sheet_name=sheet_name, index=False, header=False)
                        # Data
                        name_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3)
                st.download_button(f"Download {selected_place} File", place_io.getvalue(), f"{selected_place}_Ledger.xlsx")
        else:
            st.info("The Google Sheet is currently empty.")
    except Exception as e:
        st.error(f"Report Error: {e}")
