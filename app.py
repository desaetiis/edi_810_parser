"""
EDI 810 Parser and 997 Generator Application
"""

import streamlit as st
import pandas as pd
from edi_parser import EDI810Parser
from edi_997_generator import EDI997Generator, EDI997Config
from sftp_handler import SFTPHandler
import tempfile
import os
from datetime import datetime
import io
import traceback
import logging
from pathlib import Path
import posixpath

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='app.log', filemode='a')
logger = logging.getLogger(__name__)

# Configure logging to print to the console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)


logger.addHandler(console_handler)

# Configure Streamlit page
st.set_page_config(
    page_title="EDI Invoice Parser",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for SFTP settings
if 'sftp_connected' not in st.session_state:
    st.session_state['sftp_connected'] = False

# Initialize session state variables if they don't exist
if 'current_path' not in st.session_state:
    st.session_state['current_path'] = '.'

def init_sftp_handler():
    """Initialize SFTP handler with credentials from session state."""
    try:
        handler = SFTPHandler(
            st.session_state['sftp_host'],
            st.session_state['sftp_username'],
            st.session_state['sftp_password'],
            st.session_state['sftp_home_dir'],
            int(st.session_state['sftp_port'])
        )
        return handler
    except Exception as e:
        st.error(f"Failed to connect to SFTP server: {str(e)}")
        st.session_state['sftp_connected'] = False
        return None

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

def process_sftp_file(sftp, filename):
    """Process a file from SFTP server and display results."""
    # Download and read the file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.edi')
    try:
        sftp.download_file(f'incoming/{filename}', temp_file.name)
        temp_file.close()
        with open(temp_file.name, 'r') as f:
            content = f.read()
    finally:
        try:
            os.unlink(temp_file.name)
        except Exception:
            pass
    
    # Display original EDI content
    with st.expander("View Original EDI Content", expanded=False):
        display_edi_content(content, "Original EDI Content")
    
    # Parse EDI 810
    parser = EDI810Parser()
    invoices = parser.parse_content(content)
    
    if not invoices:
        raise ValueError("No valid invoices found in the EDI file")
    
    # Convert invoices to DataFrame for display
    invoices_df = pd.DataFrame([parser.invoice_to_dict(invoice) for invoice in invoices])
    line_items_df = parser.get_line_items_df(invoices)
    
    # Generate 997
    config = EDI997Config()
    generator = EDI997Generator(config)
    
    # Get segments for 997 generation
    segments = parser.get_997_segments()
    if not segments or not all(segments.values()):
        raise ValueError("Could not find all required segments for 997 generation")
    
    ack_997 = generator.generate_997(
        segments['ISA'],
        segments['ST'],
        segments['GS']
    )
    
    # Display 997 content
    with st.expander("View Generated 997", expanded=False):
        display_edi_content(ack_997, "997 Functional Acknowledgment")
    
    # Display invoice summary
    st.markdown("#### Invoice Summary")
    summary_columns = [
    'Invoice Number', 'Invoice Date', 'PO Number',
    'Sender ID', 'Receiver ID', 'Control Number',
    'Total Amount', 'Line Items Subtotal',
    'Total Allowances', 'Total Taxes', 'Total TDS Discounts',
    'Vendor Name', 'Buyer Name', 'Ship To Name', 'Bill To Name', 'Ship From Name'  # Add 'Ship From Name' here
]
    
    df_display = invoices_df[summary_columns].copy()
    
    # Format Total Amount with color and 2 decimal places
    styled_df = df_display.style.format({
        'Total Amount': '${:.2f}',
        'Line Items Subtotal': '${:.2f}',
        'Total Allowances': '${:.2f}',
        'Total TDS Discounts': '${:.2f}',
        'Total Taxes': '${:.2f}'
    }).apply(lambda x: ['color: #0066cc; font-weight: bold' if col == 'Total Amount' else '' for col in df_display.columns], axis=1)
    
    st.dataframe(styled_df)
    
    # Display line items
    st.markdown("#### Line Items")
    st.dataframe(line_items_df)
    
    # Success message and download button for 997
    st.success(f"✓ Successfully processed {filename}")
    st.download_button(
        label="Download 997 Acknowledgment",
        data=ack_997,
        file_name=generate_997_filename(filename),
        mime="text/plain",
        key=f"997_{filename}"
    )
    st.markdown("---")
    
    # Move processed file and save 997
    try:
        sftp.move_file(f'incoming/{filename}', f'processed/{filename}')
    except Exception as e:
        st.warning(f"Could not move processed file: {str(e)}")
        
    # Save 997 acknowledgment
    temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.997')
    try:
        temp_file.write(ack_997)
        temp_file.flush()
        temp_file.close()
        sftp.upload_file(temp_file.name, f'ack_997/{generate_997_filename(filename)}')
    finally:
        try:
            os.unlink(temp_file.name)
        except Exception:
            pass

def check_sftp_connection():
    return st.session_state.get('sftp_connected', False)


# Sidebar for SFTP configuration
with st.sidebar:
    with st.expander("SFTP Configuration", expanded=False):
        st.subheader("SFTP Configuration")
        st.session_state['sftp_host'] = st.text_input("SFTP Host", value=st.session_state.get('sftp_host', ''))
        st.session_state['sftp_port'] = st.number_input("SFTP Port", value=st.session_state.get('sftp_port', 22))
        st.session_state['sftp_username'] = st.text_input("SFTP Username", value=st.session_state.get('sftp_username', ''))
        st.session_state['sftp_password'] = st.text_input("SFTP Password", type="password", value=st.session_state.get('sftp_password', ''))
        st.session_state['sftp_home_dir'] = st.text_input("Home Directory", value=st.session_state.get('sftp_home_dir', '/'))

        # Display connection status
        if check_sftp_connection():
            st.write("🟢 Connected to SFTP")
        else:
            st.write("🔴 Disconnected from SFTP")


        # Connection buttons
        conn_col1, conn_col2 = st.columns(2)
        with conn_col1:
            connect_button = st.button(
                "Connect",
                disabled=st.session_state['sftp_connected'],
                type="primary" if not st.session_state['sftp_connected'] else "secondary"
            )

            if connect_button and not st.session_state['sftp_connected']:
                try:
                    with init_sftp_handler() as sftp:
                        sftp.connect()
                        st.session_state['sftp_connected'] = True
                        st.success("Connected to SFTP server!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to connect: {str(e)}")
                    logger.error(f"SFTP connection error: {traceback.format_exc()}")
                    st.session_state['sftp_connected'] = False
    
        with conn_col2:
            disconnect_button = st.button(
                "Disconnect",
                disabled=not st.session_state['sftp_connected'],
                type="primary" if st.session_state['sftp_connected'] else "secondary"
            )
            if disconnect_button and st.session_state['sftp_connected']:
                try:
                    with init_sftp_handler() as sftp:
                        sftp.disconnect()
                    st.session_state['sftp_connected'] = False
                    st.success("Disconnected from SFTP server")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during disconnect: {str(e)}")
                    logger.error(f"SFTP disconnect error: {traceback.format_exc()}")

# Main content area
st.title("EDI 810 Parser")

# Create main tabs for Local and SFTP operations
local_tab, sftp_tab = st.tabs(["Local Files", "SFTP Files"])

with local_tab:
    st.header("Local File Processing")


    # File uploader for local files
    uploaded_files = st.file_uploader(
        "Upload EDI files",
        type=['txt', 'edi', '810', 'dat'],
        accept_multiple_files=True,
        key="local_uploader"
    )

    if uploaded_files:
        all_invoices = []

        # Process each file
        for uploaded_file in uploaded_files:
            st.write(f"Processing: {uploaded_file.name}")

            try:
                # Save uploaded file
                file_path = save_uploaded_file(uploaded_file)

                # Display original EDI content
                with st.expander("View Original EDI Content", expanded=False):
                    display_edi_content(uploaded_file.getvalue().decode(), "Original EDI Content")

                # Parse EDI 810
                parser = EDI810Parser()
                content = uploaded_file.getvalue().decode()
                invoices = parser.parse_content(content)

                if not invoices:
                    raise ValueError("No valid invoices found in the EDI file")

                # Add invoices to the list for summary tables
                all_invoices.extend(invoices)

                # Generate 997
                config = EDI997Config()
                generator = EDI997Generator(config)

                # Get segments for 997 generation
                segments = parser.get_997_segments()
                if not segments or not all(segments.values()):
                    raise ValueError("Could not find all required segments for 997 generation")

                ack_997 = generator.generate_997(
                    segments['ISA'],
                    segments['ST'],
                    segments['GS']
                )

                # Display 997 content
                with st.expander("View Generated 997", expanded=False):
                    display_edi_content(ack_997, "997 Functional Acknowledgment")

                st.success(f"✓ Successfully processed {uploaded_file.name}")

                # Download button for 997 at the bottom
                st.download_button(
                    label="Download 997 Acknowledgment",
                    data=ack_997,
                    file_name=generate_997_filename(uploaded_file.name),
                    mime="text/plain",
                    key=f"997_{uploaded_file.name}"
                )
                st.markdown("---")

            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {str(e)}")
                logger.error(f"Error processing {uploaded_file.name}: {traceback.format_exc()}")

        # Display summary tables if we have any invoices
        if all_invoices:
            st.markdown("### Summary Tables")

            # Convert invoices to DataFrames
            invoices_df = pd.DataFrame([parser.invoice_to_dict(inv) for inv in all_invoices])
            line_items_df = parser.get_line_items_df(all_invoices)

            # Display invoice summary
            st.markdown("#### Invoice Summary")
            summary_columns = [
    'Invoice Number', 'Invoice Date', 'PO Number',
    'Sender ID', 'Receiver ID', 'Control Number', 'Transaction Type',
    'Total Amount', 'Line Items Subtotal',
    'Total Allowances', 'Total Taxes',
    'Vendor Name', 'Buyer Name', 'Ship To Name', 'Bill To Name', 'Ship From Name'  # Add 'Ship From Name' here
]
            
            df_display = invoices_df[summary_columns].copy()
            
            # Format Total Amount with color and 2 decimal places
            styled_df = df_display.style.format({
                'Total Amount': '${:.2f}',
                'Line Items Subtotal': '${:.2f}',
                'Total Allowances': '${:.2f}',
                'Total Taxes': '${:.2f}'
            }).apply(lambda x: ['color: #0066cc; font-weight: 700' if col == 'Total Amount' else '' for col in df_display.columns], axis=1)
            
            st.dataframe(styled_df)

            # Display line items
            st.markdown("#### Line Items")
            st.dataframe(line_items_df)

with sftp_tab:
    if not st.session_state['sftp_connected']:
        st.warning("Please connect to SFTP server first")
    else:
        try:
            with init_sftp_handler() as sftp:
                st.header("SFTP File Management")
                st.text(f"Current path: ./incoming")  # We're always in the incoming directory for this app
                
                with st.expander("All SFTP Files", expanded=False):
                    if st.button("🔄 Refresh", use_container_width=True):
                        # Get files from all directories
                        incoming_files = sftp.list_files('incoming')
                        processed_files = sftp.list_files('processed')
                        ack_files = sftp.list_files('ack_997')
                        
                        # Display files in a table
                        all_files = []
                        
                        # Add incoming files
                        for file in incoming_files:
                            all_files.append({
                                'Name': file['name'],
                                'Location': 'incoming',
                                'Size': f"{file['size'] / 1024:.1f} KB",
                                'Modified': file['mtime'].strftime('%Y-%m-%d %H:%M:%S')
                            })
                        
                        # Add processed files
                        for file in processed_files:
                            all_files.append({
                                'Name': file['name'],
                                'Location': 'processed',
                                'Size': f"{file['size'] / 1024:.1f} KB",
                                'Modified': file['mtime'].strftime('%Y-%m-%d %H:%M:%S')
                            })
                        
                        # Add acknowledgment files
                        for file in ack_files:
                            all_files.append({
                                'Name': file['name'],
                                'Location': 'ack_997',
                                'Size': f"{file['size'] / 1024:.1f} KB",
                                'Modified': file['mtime'].strftime('%Y-%m-%d %H:%M:%S')
                            })
                        
                        if not all_files:
                            st.info("No files found in any directory")
                        else:
                            st.dataframe(
                                all_files,
                                column_config={
                                    'Name': 'File Name',
                                    'Location': 'Directory',
                                    'Size': 'File Size',
                                    'Modified': 'Last Modified'
                                },
                                use_container_width=True
                            )
                
                # Create tabs for different SFTP operations
                incoming_tab, processed_tab, ack_tab = st.tabs(["Incoming Files", "Processed Files", "997 Acknowledgments"])
                
                with incoming_tab:
                    st.subheader("Available Files")
                    available_files = sftp.list_files('incoming')
                    if not available_files:
                        st.info("No files available in the incoming directory")
                    else:
                        file_names = [file['name'] for file in available_files]
                        selected_file = st.selectbox(
                            "Select a file to process",
                            file_names,
                            key="sftp_file_select"
                        )
                    
                    # File upload section
                    st.subheader("Upload New File")
                    uploaded_file = st.file_uploader("Choose an EDI file", type=['edi', 'txt'])
                    
                    if uploaded_file:
                        # Save uploaded file to SFTP
                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.edi')
                        try:
                            # Write content and close file before uploading
                            temp_file.write(uploaded_file.getvalue())
                            temp_file.flush()
                            temp_file.close()
                            
                            # Upload to SFTP
                            sftp.upload_file(temp_file.name, f'incoming/{uploaded_file.name}')
                            st.success(f"✓ Successfully uploaded {uploaded_file.name}")
                            
                            # Refresh available files list
                            available_files = sftp.list_files('incoming')
                            if available_files:
                                file_names = [file['name'] for file in available_files]
                                st.session_state.sftp_file_select = uploaded_file.name
                        except Exception as e:
                            st.error(f"Error uploading file: {str(e)}")
                        finally:
                            try:
                                if os.path.exists(temp_file.name):
                                    os.unlink(temp_file.name)
                            except Exception:
                                pass  # Ignore cleanup errors
                    
                    # Process selected file button
                    if available_files:
                        if st.button("Process Selected File", key="process_sftp", use_container_width=True):
                            process_sftp_file(sftp, st.session_state.sftp_file_select)
                
                with processed_tab:
                    st.subheader("Processed Files")
                    processed_files = sftp.list_files('processed')
                    if not processed_files:
                        st.info("No processed files available")
                    else:
                        for file in processed_files:
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.text(file['name'])
                            with col2:
                                if st.button("View", key=f"view_processed_{file['name']}", use_container_width=True):
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.edi') as tmp_file:
                                        sftp.download_file(f'processed/{file["name"]}', tmp_file.name)
                                        with open(tmp_file.name, 'r') as f:
                                            content = f.read()
                                        os.unlink(tmp_file.name)
                                        st.code(content, language=None)
                
                with ack_tab:
                    st.subheader("997 Acknowledgments")
                    ack_files = sftp.list_files('ack_997')
                    if not ack_files:
                        st.info("No acknowledgment files available")
                    else:
                        for file in ack_files:
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.text(file['name'])
                            with col2:
                                if st.button("View", key=f"view_ack_{file['name']}", use_container_width=True):
                                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.997')
                                    try:
                                        sftp.download_file(f"ack_997/{file['name']}", temp_file.name)
                                        temp_file.close()
                                        with open(temp_file.name, 'r') as f:
                                            content = f.read()
                                        st.code(content, language=None)
                                    finally:
                                        try:
                                            os.unlink(temp_file.name)
                                        except Exception:
                                            pass
                            with col3:
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.997')
                                try:
                                    sftp.download_file(f"ack_997/{file['name']}", temp_file.name)
                                    temp_file.close()
                                    with open(temp_file.name, 'r') as f:
                                        content = f.read()
                                    st.download_button(
                                        "Download",
                                        data=content,
                                        file_name=file['name'],
                                        mime="text/plain",
                                        key=f"download_ack_{file['name']}",
                                        use_container_width=True
                                    )
                                finally:
                                    try:
                                        os.unlink(temp_file.name)
                                    except Exception:
                                        pass
        
        except Exception as e:
            st.error(f"SFTP Error: {str(e)}")
            logger.error(f"SFTP Error: {traceback.format_exc()}")
