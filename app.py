import streamlit as st
import pandas as pd
from edi_parser import EDI810Parser
from edi_997_generator import EDI997Generator, EDI997Config
import tempfile
import os
from datetime import datetime
import io
import traceback
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='app.log', filemode='a')
logger = logging.getLogger(__name__)

# Configure logging to print to the console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Remove file handler
logger.removeHandler(logger.handlers[0])

# Configure Streamlit page
st.set_page_config(
    page_title="EDI Invoice Parser",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("EDI Invoice Parser")

def save_uploaded_file(uploaded_file):
    """Save uploaded file to temp directory and return path"""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_file.name) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_path = tmp_file.name
        return temp_path
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        logger.error(f"Error saving {uploaded_file.name}: {str(e)}")
        st.error(f"Error saving {uploaded_file.name}: {str(e)}")
        return None

def generate_997_filename(original_filename: str) -> str:
    """Generate 997 filename based on original filename"""
    base = os.path.splitext(original_filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_997_{timestamp}.edi"

def display_edi_content(content: str, title: str):
    """Display EDI content in a formatted way"""
    st.subheader(title)
    segments = content.replace("~", "~\n").split("\n")
    formatted_content = "\n".join(f"{i+1}: {seg}" for i, seg in enumerate(segments) if seg.strip())
    st.text_area("EDI Content", formatted_content, height=200)

# File uploader
uploaded_files = st.file_uploader(
    "Upload EDI files", 
    type=['txt', 'edi', '810', '791559380'], 
    accept_multiple_files=True,
    help="Upload your EDI X12 810 (Invoice) files"
)

if uploaded_files:
    all_invoices = []
    all_997s = {}
    
    # Process each file
    for uploaded_file in uploaded_files:
        temp_path = None
        try:
            logger.info(f"Processing: {uploaded_file.name}")
            st.info(f"Processing: {uploaded_file.name}")
            
            # Save uploaded file
            temp_path = save_uploaded_file(uploaded_file)
            if not temp_path:
                continue
            
            # Parse EDI file
            parser = EDI810Parser()
            with open(temp_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            # Display original EDI content
            with st.expander(f"Original EDI Content - {uploaded_file.name}"):
                display_edi_content(content, "810 Invoice Content")
            
            try:
                # Parse invoices
                invoices = parser.parse_content(content)
                if not invoices:
                    logger.warning(f"No valid invoices found in {uploaded_file.name}")
                    st.warning(f"No valid invoices found in {uploaded_file.name}")
                    continue
                    
                all_invoices.extend(invoices)
                
                # Generate 997
                try:
                    isa, st_seg, gs = parser.get_997_segments()
                    if all([isa, st_seg, gs]):
                        generator = EDI997Generator()
                        ack_997 = generator.generate_997(isa, st_seg, gs)
                        all_997s[uploaded_file.name] = (ack_997, generate_997_filename(uploaded_file.name))
                        
                        # Display 997 content
                        with st.expander(f"Generated 997 Content - {uploaded_file.name}"):
                            display_edi_content(ack_997, "997 Functional Acknowledgment")
                    else:
                        logger.warning(f"Could not generate 997 for {uploaded_file.name}: Missing required segments")
                        st.warning(f"Could not generate 997 for {uploaded_file.name}: Missing required segments")
                        if not isa:
                            logger.error("Missing ISA (Interchange Control Header) segment")
                            st.error("Missing ISA (Interchange Control Header) segment")
                        if not st_seg:
                            logger.error("Missing ST (Transaction Set Header) segment")
                            st.error("Missing ST (Transaction Set Header) segment")
                        if not gs:
                            logger.error("Missing GS (Functional Group Header) segment")
                            st.error("Missing GS (Functional Group Header) segment")
                except Exception as e:
                    logger.error(f"Error generating 997 for {uploaded_file.name}: {str(e)}")
                    logger.error(f"Traceback:\n{traceback.format_exc()}")
                    st.error(f"Error generating 997 for {uploaded_file.name}: {str(e)}")
                    st.error(f"Traceback:\n{traceback.format_exc()}")
                
            except Exception as e:
                logger.error(f"Error parsing invoice {uploaded_file.name}: {str(e)}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                st.error(f"Error parsing invoice {uploaded_file.name}: {str(e)}")
                st.error(f"Traceback:\n{traceback.format_exc()}")
            
            logger.info(f"Successfully processed {uploaded_file.name}")
            st.success(f"Successfully processed {uploaded_file.name}")
            
        except Exception as e:
            logger.error(f"Failed to process {uploaded_file.name}: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            st.error(f"Failed to process {uploaded_file.name}: {str(e)}")
            st.error(f"Traceback:\n{traceback.format_exc()}")
        finally:
            # Cleanup temp file
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    
    # Display results if we have any invoices
    if all_invoices:
        # Convert invoices to DataFrames
        invoices_df = pd.DataFrame([parser.invoice_to_dict(inv) for inv in all_invoices])
        line_items_df = parser.get_line_items_df(all_invoices)
        
        # Display invoice summary
        st.subheader("Invoice Summary")
        st.dataframe(invoices_df)
        
        # Display line items
        st.subheader("Line Items")
        st.dataframe(line_items_df)
        
        # Create columns for download buttons
        col1, col2 = st.columns(2)
        
        with col1:
            # Export to Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                invoices_df.to_excel(writer, sheet_name='Invoices', index=False)
                line_items_df.to_excel(writer, sheet_name='Line Items', index=False)
            
            excel_data = excel_buffer.getvalue()
            st.download_button(
                label="Download Excel Report",
                data=excel_data,
                file_name="edi_invoice_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            # 997 Acknowledgments
            if all_997s:
                st.subheader("997 Acknowledgments")
                for original_file, (ack_content, ack_filename) in all_997s.items():
                    st.download_button(
                        label=f"Download 997 for {original_file}",
                        data=ack_content,
                        file_name=ack_filename,
                        mime="text/plain",
                        key=f"997_{original_file}"  # Unique key for each button
                    )
    else:
        logger.warning("No valid invoices found in any of the uploaded files.")
        st.warning("No valid invoices found in any of the uploaded files.")
