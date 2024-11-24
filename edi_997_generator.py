from dataclasses import dataclass
from datetime import datetime
import re

@dataclass
class EDI997Config:
    """Configuration for EDI 997 generation"""
    segment_terminator: str = "~"
    element_separator: str = "*"
    sub_element_separator: str = ">"
    line_ending: str = "\n"
    control_version_number: str = "00401"
    functional_id_code: str = "FA"  # FA = Functional Acknowledgment
    acknowledgment_code: str = "A"  # A = Accepted

class EDI997Generator:
    """Generates EDI 997 (Functional Acknowledgment) documents"""
    
    def __init__(self, config: EDI997Config = None):
        self.config = config or EDI997Config()
        
    def validate_segments(self, isa_segment: str, st_segment: str, gs_segment: str) -> tuple[bool, str]:
        """Validate the input segments"""
        if not isa_segment or not isa_segment.startswith('ISA'):
            return False, "Missing or invalid ISA segment"
            
        if not st_segment or not st_segment.startswith('ST'):
            return False, "Missing or invalid ST segment"
            
        if not gs_segment or not gs_segment.startswith('GS'):
            return False, "Missing or invalid GS segment"
            
        try:
            isa_elements = isa_segment.split(self.config.element_separator)
            if len(isa_elements) < 16:
                return False, f"ISA segment has {len(isa_elements)} elements, expected 16"
                
            gs_elements = gs_segment.split(self.config.element_separator)
            if len(gs_elements) < 8:
                return False, f"GS segment has {len(gs_elements)} elements, expected 8"
                
            st_elements = st_segment.split(self.config.element_separator)
            if len(st_elements) < 3:
                return False, f"ST segment has {len(st_elements)} elements, expected 3"
                
        except Exception as e:
            return False, f"Error parsing segments: {str(e)}"
            
        return True, ""

    def get_current_datetime(self) -> tuple[str, str]:
        """Get current date and time in EDI format"""
        now = datetime.now()
        date = now.strftime("%y%m%d")
        time = now.strftime("%H%M")
        return date, time

    def get_control_numbers(self, isa_segment: str, st_segment: str, gs_segment: str) -> tuple[str, str, str, str]:
        """Extract control numbers from segments"""
        try:
            # Get ISA interchange control number
            isa_elements = isa_segment.split(self.config.element_separator)
            if len(isa_elements) < 14:
                raise ValueError("ISA segment missing control number (element 13)")
            isa_control = isa_elements[13].zfill(9)
            
            # Get GS group control number
            gs_elements = gs_segment.split(self.config.element_separator)
            if len(gs_elements) < 6:
                raise ValueError("GS segment missing control number (element 6)")
            gs_control = gs_elements[6]
            
            # Get ST transaction set control number
            st_elements = st_segment.split(self.config.element_separator)
            if len(st_elements) < 3:
                raise ValueError("ST segment missing control number (element 2)")
            st_control = st_elements[2]
            
            # Generate new control number for 997
            new_control = "1001"  # You might want to make this configurable
            
            return isa_control, gs_control, st_control, new_control
            
        except Exception as e:
            raise ValueError(f"Error extracting control numbers: {str(e)}")

    def generate_997(self, isa_segment: str, st_segment: str, gs_segment: str) -> str:
        """Generate a 997 functional acknowledgment"""
        # Validate input segments
        is_valid, error_msg = self.validate_segments(isa_segment, st_segment, gs_segment)
        if not is_valid:
            raise ValueError(f"Invalid input segments: {error_msg}")
        
        try:
            # Get control numbers
            isa_control, gs_control, st_control, new_control = self.get_control_numbers(isa_segment, st_segment, gs_segment)
            
            # Get current date and time
            date, time = self.get_current_datetime()
            
            # Extract sender/receiver info from ISA
            isa_elements = isa_segment.split(self.config.element_separator)
            sender_id = isa_elements[6]
            sender_qualifier = isa_elements[5]
            receiver_id = isa_elements[8]
            receiver_qualifier = isa_elements[7]
            
            # Build 997 segments
            segments = []
            
            # ISA segment (swap sender/receiver)
            isa = (f"ISA{self.config.element_separator}"
                  f"{isa_elements[1]}{self.config.element_separator}"
                  f"{isa_elements[2]}{self.config.element_separator}"
                  f"{isa_elements[3]}{self.config.element_separator}"
                  f"{isa_elements[4]}{self.config.element_separator}"
                  f"{receiver_qualifier}{self.config.element_separator}"
                  f"{receiver_id}{self.config.element_separator}"
                  f"{sender_qualifier}{self.config.element_separator}"
                  f"{sender_id}{self.config.element_separator}"
                  f"{date}{self.config.element_separator}"
                  f"{time}{self.config.element_separator}"
                  f"{self.config.control_version_number}{self.config.element_separator}"
                  f"{isa_control}{self.config.element_separator}"
                  f"0{self.config.element_separator}"
                  f"P{self.config.element_separator}"
                  f"{self.config.sub_element_separator}")
            segments.append(isa)
            
            # GS segment
            gs_elements = gs_segment.split(self.config.element_separator)
            if len(gs_elements) < 8:
                raise ValueError("Invalid GS segment format")
                
            gs = (f"GS{self.config.element_separator}"
                 f"{self.config.functional_id_code}{self.config.element_separator}"
                 f"{receiver_id}{self.config.element_separator}"
                 f"{sender_id}{self.config.element_separator}"
                 f"{date}{self.config.element_separator}"
                 f"{time}{self.config.element_separator}"
                 f"{gs_control}{self.config.element_separator}"
                 f"X{self.config.element_separator}"
                 f"{self.config.control_version_number}")
            segments.append(gs)
            
            # ST segment
            st = f"ST{self.config.element_separator}997{self.config.element_separator}{new_control}"
            segments.append(st)
            
            # AK1 segment
            ak1 = f"AK1{self.config.element_separator}{gs_elements[1]}{self.config.element_separator}{gs_control}"
            segments.append(ak1)
            
            # AK2 segment
            ak2 = f"AK2{self.config.element_separator}810{self.config.element_separator}{st_control}"
            segments.append(ak2)
            
            # AK5 segment
            ak5 = f"AK5{self.config.element_separator}{self.config.acknowledgment_code}"
            segments.append(ak5)
            
            # AK9 segment
            ak9 = f"AK9{self.config.element_separator}{self.config.acknowledgment_code}{self.config.element_separator}1{self.config.element_separator}1{self.config.element_separator}1"
            segments.append(ak9)
            
            # SE segment
            se = f"SE{self.config.element_separator}7{self.config.element_separator}{new_control}"
            segments.append(se)
            
            # GE segment
            ge = f"GE{self.config.element_separator}1{self.config.element_separator}{gs_control}"
            segments.append(ge)
            
            # IEA segment
            iea = f"IEA{self.config.element_separator}1{self.config.element_separator}{isa_control}"
            segments.append(iea)
            
            # Join segments
            return self.config.segment_terminator.join(segments) + self.config.segment_terminator
            
        except Exception as e:
            raise ValueError(f"Error generating 997: {str(e)}")
