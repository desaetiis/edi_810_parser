from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import pandas as pd

@dataclass
class EDILineItem:
    """Represents a line item in an EDI invoice"""
    line_number: str
    quantity: Decimal
    unit_price: Decimal
    uom: str
    product_code: str
    description: str = ""
    total_amount: Decimal = Decimal('0')
    allowances: List[Dict[str, Any]] = field(default_factory=list)
    taxes: List[Dict[str, Any]] = field(default_factory=list)
    gl_account: str = ""

    def __post_init__(self):
        # Calculate initial total amount
        self.total_amount = self.quantity * self.unit_price

    def add_allowance(self, allowance: Dict[str, Any]):
        """Add allowance and update total"""
        self.allowances.append(allowance)
        self.total_amount += allowance['amount']  # allowances are already negative

    def add_tax(self, tax: Dict[str, Any]):
        """Add tax and update total"""
        self.taxes.append(tax)
        self.total_amount += tax['amount']

@dataclass
class EDIInvoice:
    """Represents an EDI invoice"""
    invoice_number: str
    invoice_date: datetime
    po_number: str
    total_amount: Decimal
    vendor_name: str = ""
    buyer_name: str = ""
    currency: str = "USD"
    sender_id: str = ""
    receiver_id: str = ""
    interchange_control_number: str = ""
    line_items: List[EDILineItem] = field(default_factory=list)
    allowances: List[Dict[str, Any]] = field(default_factory=list)
    taxes: List[Dict[str, Any]] = field(default_factory=list)
    gl_account: str = ""

    def calculate_total(self) -> Decimal:
        """Calculate total amount including all line items, allowances, and taxes"""
        total = sum((item.total_amount for item in self.line_items), Decimal('0'))
        total += sum((a['amount'] for a in self.allowances), Decimal('0'))  # allowances are already negative
        total += sum((t['amount'] for t in self.taxes), Decimal('0'))
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class EDI810Parser:
    """Parser for EDI X12 810 (Invoice) documents"""
    
    def __init__(self):
        self.element_separator = '*'
        self.segment_terminator = '~'
        self.original_segments = {
            'ISA': None,
            'ST': None,
            'GS': None,
            'GE': None
        }
        
    def parse_content(self, content: str) -> List[EDIInvoice]:
        """Parse EDI content into list of invoices"""
        content = self.clean_content(content)
        self.detect_separators(content)
        
        invoices = []
        current_invoice = None
        current_line_item = None
        
        segments = content.split(self.segment_terminator)
        for segment in segments:
            if not segment.strip():
                continue
                
            elements = segment.split(self.element_separator)
            segment_id = elements[0]
            
            try:
                if segment_id == 'ISA':
                    self.original_segments['ISA'] = segment + self.segment_terminator
                    sender_id = elements[6]
                    receiver_id = elements[8]
                    interchange_control_number = elements[13]
                    
                elif segment_id == 'GS':
                    self.original_segments['GS'] = segment + self.segment_terminator
                    
                elif segment_id == 'ST':
                    self.original_segments['ST'] = segment + self.segment_terminator
                    
                elif segment_id == 'GE':
                    self.original_segments['GE'] = segment + self.segment_terminator
                    
                elif segment_id == 'BIG':
                    # Start new invoice
                    invoice_date = self.parse_date(elements[1])
                    invoice_number = elements[2]
                    po_number = elements[4] if len(elements) > 4 else ""
                    
                    current_invoice = EDIInvoice(
                        invoice_number=invoice_number,
                        invoice_date=invoice_date,
                        po_number=po_number,
                        total_amount=Decimal('0'),
                        sender_id=sender_id,
                        receiver_id=receiver_id,
                        interchange_control_number=interchange_control_number
                    )
                    invoices.append(current_invoice)
                    
                elif segment_id == 'N1':
                    # Party identification
                    if current_invoice and len(elements) > 2:
                        party_id = elements[1]
                        if party_id == 'SE':  # Selling Party
                            current_invoice.vendor_name = elements[2]
                        elif party_id == 'BY':  # Buying Party
                            current_invoice.buyer_name = elements[2]
                            
                elif segment_id == 'IT1':
                    if current_invoice:
                        quantity = Decimal(elements[2])
                        unit_price = Decimal(elements[4])
                        description = ""
                        
                        # Get description from PO1 segment if available
                        if len(elements) > 9:
                            description = elements[9]
                        
                        current_line_item = EDILineItem(
                            line_number=elements[1],
                            quantity=quantity,
                            unit_price=unit_price,
                            uom=elements[3],
                            product_code=elements[7],
                            description=description
                        )
                        current_invoice.line_items.append(current_line_item)
                        
                elif segment_id == 'PID':
                    # Product description for current line item
                    if current_line_item and len(elements) > 5:
                        current_line_item.description = elements[5]
                        
                elif segment_id == 'SAC':
                    allowance = self.parse_sac_segment(segment)
                    if allowance:
                        if current_line_item:
                            if allowance['description'] == 'SALES TAX':
                                current_line_item.add_tax(allowance)
                            else:
                                current_line_item.add_allowance(allowance)
                        elif current_invoice:
                            if allowance['description'] == 'SALES TAX':
                                current_invoice.taxes.append(allowance)
                            else:
                                current_invoice.allowances.append(allowance)
                                
                elif segment_id == 'TXI':
                    # Tax information
                    if current_invoice and len(elements) > 2:
                        tax_amount = Decimal(elements[2]) / Decimal('100')
                        tax = {'type': elements[1], 'amount': tax_amount, 'description': 'Tax'}
                        if current_line_item:
                            current_line_item.add_tax(tax)
                        else:
                            current_invoice.taxes.append(tax)
                            
                elif segment_id == 'REF' and len(elements) > 1 and elements[1] == 'CR':
                    # GL Account
                    if current_line_item:
                        current_line_item.gl_account = elements[2] if len(elements) > 2 else ""
                    elif current_invoice:
                        current_invoice.gl_account = elements[2] if len(elements) > 2 else ""

                elif segment_id == 'TDS':
                    # Total invoice amount - always in cents
                    if current_invoice and len(elements) > 1:
                        total_amount = Decimal(elements[1]) / Decimal('100')
                        current_invoice.total_amount = total_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        
                        # Verify totals match
                        calculated_total = current_invoice.calculate_total()
                        if abs(calculated_total - total_amount) > Decimal('0.02'):
                            print(f"Warning: Total mismatch for invoice {current_invoice.invoice_number}")
                            print(f"Expected: {total_amount}, Calculated: {calculated_total}")
                            print("Line items:")
                            for item in current_invoice.line_items:
                                print(f"  Line {item.line_number}: {item.total_amount}")
                            print("Allowances:")
                            for allowance in current_invoice.allowances:
                                print(f"  {allowance['description']}: {allowance['amount']}")
                            print("Taxes:")
                            for tax in current_invoice.taxes:
                                print(f"  {tax['description']}: {tax['amount']}")
                
            except Exception as e:
                print(f"Error processing segment {segment_id}: {str(e)}")
                continue
        
        return invoices

    def clean_content(self, content: str) -> str:
        """Clean EDI content by removing whitespace and normalizing line endings"""
        content = content.strip().replace('\r\n', '\n').replace('\r', '\n')
        return content.replace(self.segment_terminator + '\n', self.segment_terminator)

    def detect_separators(self, content: str):
        """Detect element separator and segment terminator from ISA segment"""
        if content.startswith('ISA'):
            self.element_separator = content[3:4]
            self.segment_terminator = content[-1]

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string in YYYYMMDD format"""
        try:
            return datetime.strptime(date_str, '%Y%m%d')
        except ValueError:
            return datetime.strptime(date_str[-6:], '%y%m%d')

    def parse_sac_segment(self, segment: str) -> Optional[Dict[str, Any]]:
        """
        Parse SAC (Service, Promotion, Allowance, or Charge Information) segment
        
        Format: SAC*A*F800***5337*******02***PROMOTIONAL ALLOWANCE~
               SAC*C*H850***2122**********SALES TAX~
        Where:
        - Element 1: Allowance or Charge Indicator (A=Allowance, C=Charge)
        - Element 2: Service/Allowance/Charge Code
        - Element 5: Amount (in cents)
        - Element 15: Description (optional)
        """
        elements = segment.split(self.element_separator)
        
        if len(elements) > 5 and elements[1] in ['A', 'C']:
            try:
                # Always treat SAC amounts as cents
                amount = Decimal(elements[5]) / Decimal('100')
                
                # Make amount negative for allowances, positive for charges
                if elements[1] == 'A':
                    amount = -amount
                
                # Get description, defaulting based on type
                if elements[1] == 'C' and elements[2] == 'H850':
                    description = "SALES TAX"
                else:
                    description = elements[15] if len(elements) > 15 and elements[15] else "PROMOTIONAL ALLOWANCE"
                
                return {
                    'type': elements[2],
                    'amount': amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    'description': description
                }
            except (IndexError, ValueError) as e:
                print(f"Warning: Error parsing SAC segment '{segment}': {str(e)}")
                return None
        return None

    def invoice_to_dict(self, invoice: EDIInvoice) -> Dict:
        """Convert invoice to dictionary for DataFrame with comprehensive totals"""
        # Calculate line item totals
        line_items_total = sum((item.total_amount for item in invoice.line_items), Decimal('0'))
        line_items_base = sum((item.quantity * item.unit_price for item in invoice.line_items), Decimal('0'))
        line_allowances = sum((sum((a['amount'] for a in item.allowances), Decimal('0')) for item in invoice.line_items), Decimal('0'))
        line_taxes = sum((sum((t['amount'] for t in item.taxes), Decimal('0')) for item in invoice.line_items), Decimal('0'))
        
        # Calculate invoice level totals
        invoice_allowances = sum((a['amount'] for a in invoice.allowances), Decimal('0'))
        invoice_taxes = sum((t['amount'] for t in invoice.taxes), Decimal('0'))
        
        # Total allowances and taxes (line item + invoice level)
        total_allowances = line_allowances + invoice_allowances
        total_taxes = line_taxes + invoice_taxes
        
        return {
            'Invoice Number': invoice.invoice_number,
            'Invoice Date': invoice.invoice_date,
            'PO Number': invoice.po_number,
            'Total Amount': float(invoice.total_amount),
            'Line Items Subtotal': float(line_items_base),
            'Line Item Allowances': float(line_allowances),
            'Line Item Taxes': float(line_taxes),
            'Invoice Allowances': float(invoice_allowances),
            'Invoice Taxes': float(invoice_taxes),
            'Total Allowances': float(total_allowances),
            'Total Taxes': float(total_taxes),
            'Vendor Name': invoice.vendor_name,
            'Buyer Name': invoice.buyer_name,
            'Currency': invoice.currency,
            'Sender ID': invoice.sender_id,
            'Receiver ID': invoice.receiver_id,
            'Control Number': invoice.interchange_control_number
        }

    def get_line_items_df(self, invoices: List[EDIInvoice]) -> pd.DataFrame:
        """Convert line items to DataFrame"""
        rows = []
        for invoice in invoices:
            for item in invoice.line_items:
                allowances = sum((a['amount'] for a in item.allowances), Decimal('0'))
                tax = sum((t['amount'] for t in item.taxes), Decimal('0'))
                
                row = {
                    'Invoice Number': invoice.invoice_number,
                    'Line Number': item.line_number,
                    'Product Code': item.product_code,
                    'Description': item.description,
                    'Quantity': float(item.quantity),
                    'Unit Price': float(item.unit_price),
                    'Line Amount': float(item.quantity * item.unit_price),
                    'Allowances': float(allowances),
                    'Sales Tax': float(tax),
                    'Net Amount': float(item.total_amount),
                    'GL Account': item.gl_account
                }
                rows.append(row)
        return pd.DataFrame(rows)

    def get_997_segments(self) -> tuple:
        """Get segments needed for 997 generation"""
        return (
            self.original_segments['ISA'],
            self.original_segments['ST'],
            self.original_segments.get('GS', None)
        )
