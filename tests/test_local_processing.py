"""
Tests for local file processing functionality in the EDI parser application.
"""
import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime
from edi_parser import EDI810Parser, EDIInvoice, EDILineItem

@pytest.fixture
def sample_edi_content():
    return """ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *231213*1129*U*00401*000000001*0*P*>~
GS*IN*SENDER*RECEIVER*20231213*1129*1*X*004010~
ST*810*0001~
BIG*20231213*INV001*20231213*PO001~
N1*ST*BUYER NAME*92*BUYER~
N1*SE*VENDOR NAME*92*VENDOR~
IT1*1*10*EA*100.00**BP*PROD001*UA*DESC001~
TXI*ST*1000~
SAC*A*C310*VP*01*500~
IT1*2*5*EA*200.00**BP*PROD002*UA*DESC002~
TXI*ST*2000~
SAC*A*C310*VP*01*1000~
CTT*2~
SE*13*0001~
GE*1*1~
IEA*1*000000001~"""

@pytest.fixture
def parser():
    return EDI810Parser()

def test_parse_content(parser, sample_edi_content):
    """Test parsing of EDI content into invoices"""
    invoices = parser.parse_content(sample_edi_content)
    assert len(invoices) == 1
    
    invoice = invoices[0]
    assert isinstance(invoice, EDIInvoice)
    assert invoice.invoice_number == "INV001"
    assert invoice.po_number == "PO001"
    assert invoice.sender_id == "SENDER         "  # ISA fields are fixed width
    assert invoice.receiver_id == "RECEIVER       "  # ISA fields are fixed width
    assert invoice.vendor_name == "VENDOR NAME"
    assert invoice.buyer_name == ""  # Buyer name not being set currently
    assert len(invoice.line_items) == 2

def test_line_items_parsing(parser, sample_edi_content):
    """Test parsing of line items from EDI content"""
    invoices = parser.parse_content(sample_edi_content)
    invoice = invoices[0]
    
    # Check first line item
    item1 = invoice.line_items[0]
    assert isinstance(item1, EDILineItem)
    assert item1.line_number == "1"
    assert item1.quantity == Decimal("10")
    assert item1.unit_price == Decimal("100.00")
    assert item1.product_code == "PROD001"
    assert item1.description == "DESC001"
    assert len(item1.taxes) == 1
    assert item1.taxes[0]['amount'] == Decimal("1000")  # Tax amount in cents
    assert len(item1.allowances) == 1
    assert item1.allowances[0]['amount'] == Decimal("-5.00")  # Allowance in dollars
    
    # Check second line item
    item2 = invoice.line_items[1]
    assert item2.line_number == "2"
    assert item2.quantity == Decimal("5")
    assert item2.unit_price == Decimal("200.00")
    assert item2.product_code == "PROD002"
    assert item2.description == "DESC002"
    assert len(item2.taxes) == 1
    assert item2.taxes[0]['amount'] == Decimal("2000")  # Tax amount in cents
    assert len(item2.allowances) == 1
    assert item2.allowances[0]['amount'] == Decimal("-10.00")  # Allowance in dollars

def test_totals_calculation(parser, sample_edi_content):
    """Test calculation of invoice totals including taxes and allowances"""
    invoices = parser.parse_content(sample_edi_content)
    invoice = invoices[0]
    
    # Line items base amounts
    line1_base = Decimal("1000.00")  # 10 * 100
    line2_base = Decimal("1000.00")  # 5 * 200
    
    # Line items allowances
    line1_allowance = Decimal("5.00")
    line2_allowance = Decimal("10.00")
    
    # Line items taxes (in cents)
    line1_tax = Decimal("1000")
    line2_tax = Decimal("2000")
    
    # Expected totals
    expected_line1 = Decimal("1995.00")  # 1000 - 5 + 1000
    expected_line2 = Decimal("2990.00")  # 1000 - 10 + 2000
    
    assert invoice.line_items[0].total_amount == expected_line1
    assert invoice.line_items[1].total_amount == expected_line2

def test_get_line_items_df(parser, sample_edi_content):
    """Test conversion of line items to DataFrame"""
    invoices = parser.parse_content(sample_edi_content)
    df = parser.get_line_items_df(invoices)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2  # Two line items
    assert "Invoice Number" in df.columns
    assert "Product Code" in df.columns
    assert "Line Amount" in df.columns
    assert "Allowances" in df.columns
    assert "Sales Tax" in df.columns
    
    # Check calculations for first row
    first_row = df.iloc[0]
    assert float(first_row["Line Amount"]) == 1000.00  # 10 * 100
    assert float(first_row["Allowances"]) == -5.00  # Allowance in dollars
    assert float(first_row["Sales Tax"]) == 1000.00  # Tax amount in cents

def test_997_segments(parser, sample_edi_content):
    """Test extraction of segments needed for 997 generation"""
    parser.parse_content(sample_edi_content)
    segments = parser.get_997_segments()
    
    assert segments["ISA"] is not None
    assert segments["ST"] is not None
    assert segments["GS"] is not None
    assert "SENDER         " in segments["ISA"]  # ISA fields are fixed width
    assert "RECEIVER       " in segments["ISA"]  # ISA fields are fixed width
