# EDI 810 Invoice Parser

A robust Python-based tool for parsing EDI X12 810 (Invoice) documents with a Streamlit web interface. Features intelligent amount parsing, comprehensive trading partner information extraction, and automatic 997 acknowledgment generation.

## Features

### Core Functionality
- Parse EDI X12 810 (Invoice) files with flexible format support
- Intelligent amount parsing (auto-detects dollar/cent formats)
- Trading partner information extraction
- Automatic 997 (Functional Acknowledgment) generation
- Batch processing of multiple EDI files
- Excel export functionality
- User-friendly web interface

### Data Extraction
- Invoice Level Information:
  - Invoice number and date
  - PO number
  - Total amount (with automatic dollar/cent detection)
  - Vendor and buyer information
  - Currency
  - Sender/Receiver IDs and qualifiers
  - Interchange control numbers
- Line Item Details:
  - Line number
  - Product code
  - Quantity
  - Unit price
  - Unit of measure
  - Description
  - Total line amount

### Advanced Features
- Automatic dollar/cent format detection
- Amount validation and reconciliation
- Trading partner identification
- Flexible file format support
- Robust preprocessing
- EDI 997 acknowledgment generation

## Installation

1. Clone the repository
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the web application:
   ```bash
   streamlit run app.py
   ```
2. Upload your EDI files (*.txt, *.edi, *.810)
3. View extracted information
4. Download Excel report and 997 acknowledgments

## Supported EDI Segments

### EDI 810 (Invoice)
- ISA: Interchange Control Header
- ST: Transaction Set Header
- BIG: Beginning Segment for Invoice
- N1: Name Segment (Party Identification)
- IT1: Baseline Item Data
- TDS: Total Monetary Value Summary
- CUR: Currency
- SE: Transaction Set Trailer

### EDI 997 (Functional Acknowledgment)
- AK1: Functional Group Response Header
- AK2: Transaction Set Response Header
- AK5: Transaction Set Response Trailer
- AK9: Functional Group Response Trailer

## Data Validation

- Amount Format Detection
- Trading Partner Validation
- Error Handling

## Technical Details

### Amount Processing
- Supports both dollar and cent formats
- Automatic format detection based on total validation
- Precise decimal handling using Python's Decimal type
- Configurable rounding behavior

### File Processing
- Robust preprocessing for various file formats
- Flexible segment terminator handling
- UTF-8 encoding support with BOM handling
- Efficient batch processing

## Requirements

- Python 3.7+
- Dependencies listed in requirements.txt

## License

MIT License
