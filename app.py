import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
from datetime import datetime
from PIL import Image
import io

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Telugu Ledger AI", layout="wide")
st.title("📲 Telugu Ledger Smart App")

# --- 2. AUTHENTICATION & SECRETS ---
# This looks for the API key in Streamlit Secrets first
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    with st.sidebar:
        api_key = st.text_input("Enter Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)

# Get Google Sheet URL from Secrets
if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    # Convert standard URL to direct CSV download URL to avoid HTTP Errors
    csv_url = sheet_url.replace('/edit?usp=sharing', '/export?format=csv').replace('/edit#gid=', '/export?format=csv&gid=')
else:
    st.error("⚠️ Google Sheet URL missing in Secrets!")
    st.stop()

# --- 3. AI PROCESSING LOGIC ---
def extract_ledger_data(img_file):
    model = genai.GenerativeModel('gemini-2.5-flash')
    img = Image.open(img_file)
    prompt = """
    Extract handwritten ledger data into a JSON list.
    Columns: Date, Place, Name, Item, Amount, Paid.
    - If Date is missing, use "".
    - If Paid is empty, use 0.
    - Transcribe Telugu names exactly as written.
    - Repeat the 'Place' for all names listed under it.
    Return ONLY valid JSON.
    """
    try:
        response = model.generate_content([prompt, img])
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Reading Error: {e}")
        return None

# --- 4. USER INTERFACE TABS ---
tab1, tab2 = st.tabs(["📤 Upload Ledger", "📥 Download Reports"])

with tab1:
    uploaded_files = st.file_uploader("Upload or Take Photos", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
    if st.button("Process & Show Table"):
        if not api_key:
            st.error("Please provide an API Key.")
        else:
            all_new_data = []
            for f in uploaded_files:
                with st.spinner(f"Reading {f.name}..."):
                    items = extract_ledger_data(f)
                    if items:
                        for i in items:
                            i['Date'] = i.get('Date') or datetime.now().strftime("%d/%m/%Y")
                            amt = float(i.get('Amount', 0))
                            paid = float(i.get('Paid', 0))
                            i['Amount'], i['Paid'] = amt, paid
                            i['Balance'] = amt - paid
                            all_new_data.append(i)
            
            if all_new_data:
                st.success("Processing Complete!")
                new_df = pd.DataFrame(all_new_data)
                st.write("### New Transactions Found:")
                st.dataframe(new_df)
                
                # Instruction for the user
                st.info("💡 Since this is a public app, please copy the table above and paste it into your Google Sheet to save it permanently.")
            else:
                st.warning("No data could be extracted.")

with tab2:
    try:
        # Read the latest data from the Google Sheet
        master_df = pd.read_csv(csv_url)
        
        if not master_df.empty:
            st.subheader("Organized Excel Reports")
            
            # --- Master Workbook ---
            master_io = io.BytesIO()
            with pd.ExcelWriter(master_io, engine='openpyxl') as writer:
                for p in master_df['Place'].unique():
                    p_name = str(p) if p else "Unknown"
                    summary = master_df[master_df['Place'] == p].groupby('Name')['Balance'].sum().reset_index()
                    summary.to_excel(writer, sheet_name=p_name[:30], index=False)
            
            st.download_button("Download Master Balance Sheet", master_io.getvalue(), "Master_Balance.xlsx")
            
            st.write("---")
            
            # --- Individual Place Workbook ---
            selected_place = st.selectbox("Select Place for Detailed Sheets", master_df['Place'].unique())
            if st.button(f"Generate {selected_place} Workbook"):
                place_df = master_df[master_df['Place'] == selected_place]
                place_io = io.BytesIO()
                with pd.ExcelWriter(place_io, engine='openpyxl') as writer:
                    for name in place_df['Name'].unique():
                        name_df = place_df[place_df['Name'] == name]
                        sheet_name = str(name)[:30].replace('/', '-')
                        
                        # Widget header
                        pd.DataFrame([["NAME:", name], ["TOTAL BALANCE:", name_df['Balance'].sum()]]).to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=0)
                        # Data table
                        name_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3)
                
                st.download_button(f"Download {selected_place}_Detailed_Ledger.xlsx", place_io.getvalue(), f"{selected_place}_Ledger.xlsx")
    except Exception as e:
        st.warning("No data found in your Google Sheet yet. Make sure it is Shared as 'Anyone with link'.")
