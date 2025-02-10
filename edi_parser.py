from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import pandas as pd
import streamlit as st

@dataclass
class EDILineItem:
    """
    Represents a line item in an EDI invoice
    
    Args:
        line_number (str): The line item number
        quantity (Decimal): The quantity of items
        unit_price (Decimal): The price per unit
        uom (str): Unit of measure
        product_code (str): Product code identifier
        description (str, optional): Product description. Defaults to empty string
        total_amount (Decimal, optional): Total amount for the line item. Defaults to 0
        allowances (List[Dict[str, Any]], optional): List of allowances. Defaults to empty list
        taxes (List[Dict[str, Any]], optional): List of taxes. Defaults to empty list
        gl_account (str, optional): GL account number. Defaults to empty string
    """
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
    _transaction_type: str = field(default="", init=False)

    def __post_init__(self):
        # Calculate initial total amount
        self.total_amount = self.quantity * self.unit_price

    def set_transaction_type(self, transaction_type: str):
        """
        Set the transaction type and adjust amounts accordingly
        
        Args:
            transaction_type (str): The transaction type (e.g., 'CR' for credit)
        """
        self._transaction_type = transaction_type
        if transaction_type == 'CR':
            self.total_amount = -abs(self.total_amount)

    def add_allowance(self, allowance: Dict[str, Any]):
        """
        Add allowance and update total
        
        Args:
            allowance (Dict[str, Any]): Allowance information
        """
        self.allowances.append(allowance)
        amount = allowance['amount']
        if self._transaction_type == 'CR':
            amount = -abs(amount)
        self.total_amount += amount

    def add_tax(self, tax: Dict[str, Any]):
        """
        Add tax and update total
        
        Args:
            tax (Dict[str, Any]): Tax information
        """
        self.taxes.append(tax)
        amount = tax['amount']
        if self._transaction_type == 'CR':
            amount = -abs(amount)
        self.total_amount += amount

@dataclass
class EDIInvoice:
    """
    Represents an EDI invoice
    
    Args:
        invoice_number (str): The invoice number
        invoice_date (datetime): The invoice date
        po_number (str): Purchase order number
        total_amount (Decimal): Total invoice amount
        vendor_name (str, optional): Name of the vendor. Defaults to empty string
        buyer_name (str, optional): Name of the buyer. Defaults to empty string
        ship_to_name (str, optional): Name of the ship to party. Defaults to empty string
        bill_to_name (str, optional): Name of the bill to party. Defaults to empty string
        ship_from_name (str, optional): Name of the ship from party. Defaults to empty string
        currency (str, optional): Currency code. Defaults to "USD"
        sender_id (str, optional): Sender identifier. Defaults to empty string
        receiver_id (str, optional): Receiver identifier. Defaults to empty string
        interchange_control_number (str, optional): Control number. Defaults to empty string
        line_items (List[EDILineItem], optional): List of line items. Defaults to empty list
        allowances (List[Dict[str, Any]], optional): List of invoice-level allowances. Defaults to empty list
        taxes (List[Dict[str, Any]], optional): List of invoice-level taxes. Defaults to empty list
        gl_account (str, optional): GL account number. Defaults to empty string
        transaction_type (str, optional): Transaction type (e.g., 'CR' for credit). Defaults to empty string
    """
    invoice_number: str
    invoice_date: datetime
    po_number: str
    total_amount: Decimal
    vendor_name: str = ""
    buyer_name: str = ""
    ship_to_name: str = ""
    bill_to_name: str = ""
    ship_from_name: str = ""
    currency: str = "USD"
    sender_id: str = ""
    receiver_id: str = ""
    interchange_control_number: str = ""
    line_items: List[EDILineItem] = field(default_factory=list)
    allowances: List[Dict[str, Any]] = field(default_factory=list)
    taxes: List[Dict[str, Any]] = field(default_factory=list)
    gl_account: str = ""
    transaction_type: str = ""
    total_tax: Decimal = field(default=Decimal('0'), init=False)

    def calculate_total(self) -> Decimal:
        """
        Calculate total amount including all line items, allowances, and taxes

        Returns:
            Decimal: The total amount
        """
        # Calculate line items total
        total = sum((item.quantity * item.unit_price for item in self.line_items), Decimal('0'))

        # Add line item allowances
        total += sum((sum((a['amount'] for a in item.allowances), Decimal('0')) for item in self.line_items),
                     Decimal('0'))

        # Add invoice level allowances
        total += sum((a['amount'] for a in self.allowances), Decimal('0'))

        # Add tax - use total_tax if present, otherwise sum invoice-level taxes
        if self.total_tax > Decimal('0'):
            total += self.total_tax
        else:
            total += sum((t['amount'] for t in self.taxes), Decimal('0'))

        # Handle credit transactions
        if self.transaction_type == 'CR':
            total = -abs(total)

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
                    self.original_segments['ISA'] = segment.strip()
                    sender_id = elements[6]
                    receiver_id = elements[8]
                    interchange_control_number = elements[13]
                    
                elif segment_id == 'GS':
                    self.original_segments['GS'] = segment.strip()
                    
                elif segment_id == 'ST':
                    self.original_segments['ST'] = segment.strip()
                    
                elif segment_id == 'GE':
                    self.original_segments['GE'] = segment.strip()
                    
                elif segment_id == 'BIG':
                    # Start new invoice
                    invoice_date = self.parse_date(elements[1])
                    invoice_number = elements[2]
                    po_number = elements[5] if len(elements) > 5 else ""
                    transaction_type = elements[-1] if len(elements) > 6 else ""
                    
                    current_invoice = EDIInvoice(
                        invoice_number=invoice_number,
                        invoice_date=invoice_date,
                        po_number=po_number,
                        total_amount=Decimal('0'),
                        sender_id=sender_id,
                        receiver_id=receiver_id,
                        interchange_control_number=interchange_control_number,
                        transaction_type=transaction_type
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
                        elif party_id == 'ST':  # Ship To Party
                            current_invoice.ship_to_name = elements[2]
                        elif party_id == 'BT':  # Bill To Party
                            current_invoice.bill_to_name = elements[2]
                        elif party_id == 'SF':  # Ship From Party
                            current_invoice.ship_from_name = elements[2]
                            
                elif segment_id == 'IT1':
                    if current_invoice:
                        quantity = Decimal(elements[2])
                        unit_price = Decimal(elements[4])
                        description = ""
                        gl_account = ""
                        
                        # Get description from PO1 segment if available
                        if len(elements) > 9:
                            description = elements[9]
                        
                        current_line_item = EDILineItem(
                            line_number=elements[1],
                            quantity=quantity,
                            unit_price=unit_price,
                            uom=elements[3],
                            product_code=elements[7],
                            description=description,
                            gl_account=elements[-1]
                        )
                        # Set transaction type to handle credit amounts
                        current_line_item.set_transaction_type(current_invoice.transaction_type)
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
                        tax_type = elements[1]
                        # TXI amounts are in dollars, not cents
                        tax_amount = Decimal(elements[2])
                        # Check if amount needs to be converted from cents
                        if '.' not in elements[2]:
                            tax_amount = tax_amount / Decimal('100')

                        # For invoice-level tax total (TX) or McLane sales tax (LS)
                        if tax_type in ['TX', 'LS']:
                            current_invoice.total_tax = tax_amount
                        # For other tax types, only add to line item if we're certain it belongs there
                        else:
                            tax = {'type': tax_type, 'amount': tax_amount, 'description': 'Tax'}
                            # You might need additional logic here to determine if the tax belongs to a line item
                            # For now, we'll add it to the invoice level to be safe
                            current_invoice.taxes.append(tax)
                            
                elif segment_id == 'REF' and len(elements) > 1 and (elements[1] == 'PG' or elements[1] == 'CR'):
                    # GL Account
                    if current_line_item:
                        current_line_item.gl_account = elements[2] if len(elements) > 2 else ""
                    elif current_invoice:
                        current_invoice.gl_account = elements[2] if len(elements) > 2 else ""

                elif segment_id == 'TDS':
                    total_amount = Decimal(elements[1])
                    tds_discount = Decimal(elements[4]) if len(elements) > 3 else Decimal('0')
                    # Total invoice amount - always in cents if no decimal point found
                    if current_invoice and len(elements) > 1:
                        if '.' in elements[1]: # leave as is
                            pass
                        else: # no decimal point, assume cents
                            total_amount = Decimal(elements[1]) / Decimal('100')
                            tds_discount = Decimal(elements[4]) / Decimal('100') if len(elements) > 3 else Decimal('0')
                        # Adjust for discount
                        if tds_discount > Decimal('0'):
                            current_invoice.allowances.append(tds_discount)
                        
                        # Adjust total amount for credit transactions
                        if current_invoice.transaction_type == 'CR':
                            total_amount = -abs(total_amount)
                            
                        current_invoice.total_amount = total_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        
                        # Verify totals match
                        calculated_total = current_invoice.calculate_total()
                        if abs(calculated_total - total_amount) > Decimal('0.02'):
                            with st.expander(f"Mismatch Details for Invoice {current_invoice.invoice_number}"):
                                # Calculate line items base total without tax
                                line_items_base_total = sum((item.quantity * item.unit_price for item in current_invoice.line_items), Decimal('0'))
                                line_items_allowances = sum(
                                    (sum((a['amount'] for a in item.allowances), Decimal('0')) for item in current_invoice.line_items), Decimal('0'))
                                invoice_allowances = sum((a['amount'] for a in current_invoice.allowances), Decimal('0'))
                                
                                # Adjust for credit transactions
                                if current_invoice.transaction_type == 'CR':
                                    line_items_base_total = -abs(line_items_base_total)
                                    line_items_allowances = -abs(line_items_allowances)
                                    invoice_allowances = -abs(invoice_allowances)
                                
                                subtotal_without_tax = line_items_base_total + line_items_allowances + invoice_allowances
                                
                                # Header with basic mismatch info and subtotal comparison
                                st.code(f"Total Mismatch for Invoice {current_invoice.invoice_number}\n" +
                                      f"Expected (TDS): {total_amount}\n" +
                                      f"Calculated:     {calculated_total}\n" +
                                      f"Difference:     {abs(calculated_total - total_amount)}\n" +
                                      f"Subtotal (without tax): {subtotal_without_tax}")
                                
                                # Detailed breakdown of line items
                                line_items_detail = ["Line Items Breakdown:"]
                                line_items_subtotal = Decimal('0')
                                for item in current_invoice.line_items:
                                    base_amount = item.quantity * item.unit_price
                                    item_allowances = sum((a['amount'] for a in item.allowances), Decimal('0'))
                                    item_taxes = sum((t['amount'] for t in item.taxes), Decimal('0'))
                                    
                                    if current_invoice.transaction_type == 'CR':
                                        base_amount = -abs(base_amount)
                                        item_allowances = -abs(item_allowances)
                                        item_taxes = -abs(item_taxes)
                                        
                                    line_total = base_amount + item_allowances + item_taxes
                                    line_items_subtotal += line_total
                                    
                                    line_items_detail.append(
                                        f"  Line {item.line_number}:\n" +
                                        f"    Quantity: {item.quantity} × Price: {item.unit_price} = Base: {base_amount}\n" +
                                        f"    Allowances: {item_allowances}\n" +
                                        f"    Taxes: {item_taxes}\n" +
                                        f"    Line Total: {line_total}"
                                    )
                                line_items_detail.append(f"Line Items Subtotal: {line_items_subtotal}\n")
                                st.code("\n".join(line_items_detail))
                                
                                # Invoice level charges
                                invoice_allowances = sum((a['amount'] for a in current_invoice.allowances), Decimal('0'))
                                invoice_discounts = tds_discount
                                invoice_taxes = sum((t['amount'] for t in current_invoice.taxes), Decimal('0'))
                                
                                if current_invoice.transaction_type == 'CR':
                                    invoice_allowances = -abs(invoice_allowances)
                                    invoice_discounts = -abs(invoice_discounts)
                                    invoice_taxes = -abs(invoice_taxes)
                                
                                st.code("Invoice Level Charges:\n" +
                                      f"  Allowances: {invoice_allowances}\n" +
                                        f"  Discounts: {invoice_discounts}\n" +
                                      f"  Taxes: {invoice_taxes}\n")
                                
                                # Final calculation breakdown
                                st.code("Final Calculation:\n" +
                                      f"  Line Items Subtotal: {line_items_subtotal}\n" +
                                      f"  Invoice Allowances: {invoice_allowances}\n" +
                                      f"  Invoice discounts: {invoice_discounts}\n" +
                                      f"  Invoice Taxes: {invoice_taxes}\n" +
                                      f"  Calculated Total: {calculated_total}")
            except Exception as e:
                st.warning(f"Error processing segment {segment_id}: {str(e)}")
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
                st.warning(f"Warning: Error parsing SAC segment '{segment}': {str(e)}")
                return None
        return None

    def invoice_to_dict(self, invoice: EDIInvoice) -> Dict:
        """
        Convert invoice to dictionary for DataFrame with comprehensive totals

        Args:
            invoice (EDIInvoice): The invoice to convert

        Returns:
            Dict: Dictionary containing invoice data and calculated totals
        """
        # Calculate line item totals
        line_items_base = sum((item.quantity * item.unit_price for item in invoice.line_items), Decimal('0'))
        line_allowances = sum(
            (sum((a['amount'] for a in item.allowances), Decimal('0')) for item in invoice.line_items), Decimal('0'))

        # Calculate invoice level totals
        invoice_allowances = sum((a['amount'] for a in invoice.allowances), Decimal('0'))

        # Calculate total taxes once
        if invoice.total_tax > Decimal('0'):
            total_taxes = invoice.total_tax
        else:
            total_taxes = sum((t['amount'] for t in invoice.taxes), Decimal('0'))

        # Handle credit transactions
        if invoice.transaction_type == 'CR':
            line_items_base = -abs(line_items_base)
            line_allowances = -abs(line_allowances)
            invoice_allowances = -abs(invoice_allowances)
            total_taxes = -abs(total_taxes)

        # Total allowances (line item + invoice level)
        total_allowances = line_allowances + invoice_allowances

        # Calculate subtotal before tax
        subtotal = line_items_base + total_allowances

        # Total amount is subtotal plus tax
        total_amount = subtotal + total_taxes

        return {
            'Invoice Number': invoice.invoice_number,
            'Invoice Date': invoice.invoice_date,
            'PO Number': invoice.po_number,
            'Total Amount': float(total_amount),
            'Line Items Subtotal': float(line_items_base),
            'Total Allowances': float(total_allowances),
            'Total Discounts': float(invoice_allowances),
            'Total Taxes': float(total_taxes),
            'Control Number': invoice.interchange_control_number,
            'Vendor Name': invoice.vendor_name,
            'Buyer Name': invoice.buyer_name,
            'Ship To Name': invoice.ship_to_name,
            'Bill To Name': invoice.bill_to_name,
            'Ship From Name': invoice.ship_from_name,
            'Currency': invoice.currency,
            'Sender ID': invoice.sender_id,
            'Receiver ID': invoice.receiver_id,
            'Transaction Type': invoice.transaction_type
        }

    def get_line_items_df(self, invoices: List[EDIInvoice]) -> pd.DataFrame:
        """
        Convert line items to DataFrame
        
        Args:
            invoices (List[EDIInvoice]): List of invoices to convert
            
        Returns:
            pd.DataFrame: DataFrame containing line item data
        """
        rows = []
        for invoice in invoices:
            for item in invoice.line_items:
                # Calculate base amount
                base_amount = item.quantity * item.unit_price
                
                # Calculate allowances and taxes
                allowances = sum((a['amount'] for a in item.allowances), Decimal('0'))
                tax = sum((t['amount'] for t in item.taxes), Decimal('0'))
                
                # Adjust amounts for credit transactions
                if invoice.transaction_type == 'CR':
                    base_amount = -abs(base_amount)
                    allowances = -abs(allowances)
                    tax = -abs(tax)
                
                # Calculate net amount
                net_amount = base_amount + allowances + tax
                
                row = {
                    'Invoice Number': invoice.invoice_number,
                    'Line Number': item.line_number,
                    'Product Code': item.product_code,
                    'Description': item.description,
                    'Quantity': float(item.quantity),
                    'Unit Price': float(item.unit_price),
                    'Line Amount': float(base_amount),
                    'Allowances': float(allowances),
                    'Sales Tax': float(tax),
                    'Net Amount': float(net_amount),
                    'GL Account': item.gl_account,
                    'Transaction Type': invoice.transaction_type
                }
                rows.append(row)
        return pd.DataFrame(rows)

    def get_997_segments(self) -> Dict[str, str]:
        """Get segments needed for 997 generation"""
        return self.original_segments
