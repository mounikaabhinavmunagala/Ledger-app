import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
from datetime import datetime
from PIL import Image
import io

# App Config
st.set_page_config(page_title="Telugu Ledger AI", layout="wide")
st.title("📑 Telugu Ledger Smart App")

# Connection to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Sidebar for Setup
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("AIzaSyDfnrGBt1DHnDwkqkqTHk_WFQEZrpI2ZWo", type="password")
    if api_key:
        genai.configure(api_key=api_key)

def extract_data(img_file):
    model = genai.GenerativeModel('gemini-2.5-flash')
    img = Image.open(img_file)
    prompt = """Extract handwritten ledger to JSON array. 
    Columns: Date, Place, Name, Item, Amount, Paid. 
    If Date is missing use "". If Paid is empty use 0."""
    response = model.generate_content([prompt, img])
    try:
        text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(text)
    except: return None

tab1, tab2 = st.tabs(["📤 Upload Ledger", "📥 Download Reports"])

with tab1:
    files = st.file_uploader("Upload Ledger Photos", type=['jpg', 'png'], accept_multiple_files=True)
    if st.button("Save to Google Sheets"):
        if not api_key: st.error("Please add API Key")
        else:
            existing_df = conn.read(worksheet="Sheet1", ttl=0)
            new_data = []
            for f in files:
                with st.spinner(f"Reading {f.name}..."):
                    items = extract_data(f)
                    if items:
                        for i in items:
                            i['Date'] = i.get('Date') or datetime.now().strftime("%d/%m/%Y")
                            i['Balance'] = float(i.get('Amount', 0)) - float(i.get('Paid', 0))
                            new_data.append(i)
            
            updated_df = pd.concat([existing_df, pd.DataFrame(new_data)], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            st.success("Database Updated!")

with tab2:
    df = conn.read(worksheet="Sheet1", ttl=0)
    if not df.empty:
        st.subheader("Generate Organized Workbooks")
        
        # 1. Master Balance Sheet
        master_out = io.BytesIO()
        with pd.ExcelWriter(master_out, engine='openpyxl') as writer:
            for p in df['Place'].unique():
                df[df['Place'] == p].groupby('Name')['Balance'].sum().reset_index().to_excel(writer, sheet_name=str(p)[:30], index=False)
        st.download_button("Download Master Balance Workbook", master_out.getvalue(), "Master_Balance.xlsx")

        # 2. Place-wise Detail Workbook
        place_sel = st.selectbox("Select Place for Detail Workbook", df['Place'].unique())
        if st.button(f"Create Workbook for {place_sel}"):
            place_df = df[df['Place'] == place_sel]
            place_out = io.BytesIO()
            with pd.ExcelWriter(place_out, engine='openpyxl') as writer:
                for n in place_df['Name'].unique():
                    n_df = place_df[place_df['Name'] == n]
                    # Header Widget
                    pd.DataFrame([["NAME:", n], ["TOTAL BALANCE:", n_df['Balance'].sum()]]).to_excel(writer, sheet_name=str(n)[:30], index=False, header=False, startrow=0)
                    n_df.to_excel(writer, sheet_name=str(n)[:30], index=False, startrow=3)
            st.download_button(f"Download {place_sel}_Ledger.xlsx", place_out.getvalue(), f"{place_sel}_Ledger.xlsx")
