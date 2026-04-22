import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
from datetime import datetime
from PIL import Image
import io
import urllib.parse

# --- CONFIG ---
st.set_page_config(page_title="Telugu Ledger AI", layout="wide")
st.title("📑 Telugu Ledger Smart App")

# --- SETTINGS & API ---
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("AIzaSyDfnrGBt1DHnDwkqkqTHk_WFQEZrpI2ZWo", type="password")
    if api_key:
        genai.configure(api_key=api_key)

# Helper function to convert Google Sheet URL to direct Download URL
def get_csv_url(url):
    try:
        # Converts /edit... to /export?format=csv
        base_url = url.split('/edit')[0]
        return f"{base_url}/export?format=csv"
    except:
        return url

# --- DATA PROCESSING ---
def extract_data(img_file):
    model = genai.GenerativeModel('gemini-2.5-flash')
    img = Image.open(img_file)
    prompt = """Extract ledger data to JSON array. 
    Columns: Date, Place, Name, Item, Amount, Paid. 
    If Date is missing use "". If Paid is empty use 0.
    Ensure Telugu names are transcribed exactly as written."""
    
    try:
        response = model.generate_content([prompt, img])
        text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(text)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- UI TABS ---
tab1, tab2 = st.tabs(["📤 Upload Ledger", "📥 Download Reports"])

# Check if Spreadsheet URL exists in Secrets
if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = get_csv_url(sheet_url)
else:
    st.error("Please add your Google Sheet URL to Streamlit Secrets!")
    st.stop()

with tab1:
    files = st.file_uploader("Upload Ledger Photos", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
    
    if st.button("Process Ledger"):
        if not api_key:
            st.error("Please add your Gemini API Key in the sidebar.")
        else:
            # 1. Read existing data directly via CSV URL
            try:
                df = pd.read_csv(csv_url)
            except:
                # If sheet is empty/unreachable
                df = pd.DataFrame(columns=['Date', 'Place', 'Name', 'Item', 'Amount', 'Paid', 'Balance'])

            new_entries = []
            for f in files:
                with st.spinner(f"Reading {f.name}..."):
                    items = extract_data(f)
                    if items:
                        for i in items:
                            i['Date'] = i.get('Date') or datetime.now().strftime("%d/%m/%Y")
                            amt = float(i.get('Amount', 0))
                            paid = float(i.get('Paid', 0))
                            i['Amount'] = amt
                            i['Paid'] = paid
                            i['Balance'] = amt - paid
                            new_entries.append(i)
            
            if new_entries:
                updated_df = pd.concat([df, pd.DataFrame(new_entries)], ignore_index=True)
                
                # --- INSTRUCTION ---
                st.success("Data Processed! Since we are using the 'Read-Only' CSV method for speed:")
                st.info("1. Copy the table below.")
                st.info("2. Paste it into your Google Sheet.")
                st.dataframe(pd.DataFrame(new_entries))
            else:
                st.warning("No data found in images.")

with tab2:
    try:
        df = pd.read_csv(csv_url)
        if not df.empty:
            st.subheader("Generate Organized Workbooks")
            
            # Master Workbook
            master_out = io.BytesIO()
            with pd.ExcelWriter(master_out, engine='openpyxl') as writer:
                for p in df['Place'].unique():
                    p_name = str(p) if p else "Unknown"
                    df[df['Place'] == p].groupby('Name')['Balance'].sum().reset_index().to_excel(writer, sheet_name=p_name[:30], index=False)
            st.download_button("Download Master Balance Workbook", master_out.getvalue(), "Master_Balance.xlsx")

            # Place-wise Workbook
            place_sel = st.selectbox("Select Place for Detailed Workbook", df['Place'].unique())
            if st.button(f"Create Workbook for {place_sel}"):
                place_df = df[df['Place'] == place_sel]
                place_out = io.BytesIO()
                with pd.ExcelWriter(place_out, engine='openpyxl') as writer:
                    for n in place_df['Name'].unique():
                        n_df = place_df[place_df['Name'] == n]
                        # Widget
                        pd.DataFrame([["NAME:", n], ["TOTAL BALANCE:", n_df['Balance'].sum()]]).to_excel(writer, sheet_name=str(n)[:30], index=False, header=False, startrow=0)
                        n_df.to_excel(writer, sheet_name=str(n)[:30], index=False, startrow=3)
                st.download_button(f"Download {place_sel}_Ledger.xlsx", place_out.getvalue(), f"{place_sel}_Ledger.xlsx")
    except:
        st.warning("No data found in the Google Sheet yet.")
