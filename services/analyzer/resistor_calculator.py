import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Union, Optional

# Common SMD resistor case sizes and their typical power ratings in watts
# This is a simplified table. Power rating can vary by manufacturer and series.
SMD_POWER_RATINGS = {
    '01005': 0.031,
    '0201': 0.05,
    '0402': 0.062,
    '0603': 0.1,
    '0805': 0.125,
    '1206': 0.25,
    '1210': 0.5,
    '1812': 0.75,
    '2010': 0.75,
    '2512': 1.0,
}

# EIA-96 1% SMD Resistor Codes (Value Multiplier)
EIA96_MULTIPLIERS = {
    'Z': 0.001, 'Y': 0.01, 'X': 0.1, 'A': 1,
    'B': 10, 'C': 100, 'D': 1000, 'E': 10000,
    'F': 100000, 'G': 1000000, 'H': 10000000
}

# EIA-96 Code to significant digits mapping
EIA96_CODES = {
    '01': 100, '02': 102, '03': 105, '04': 107, '05': 110, '06': 113, '07': 115, '08': 118, '09': 121, '10': 124,
    '11': 127, '12': 130, '13': 133, '14': 137, '15': 140, '16': 143, '17': 147, '18': 150, '19': 154, '20': 158,
    '21': 162, '22': 165, '23': 169, '24': 174, '25': 178, '26': 182, '27': 187, '28': 191, '29': 196, '30': 200,
    '31': 205, '32': 210, '33': 215, '34': 221, '35': 226, '36': 232, '37': 237, '38': 243, '39': 249, '40': 255,
    '41': 261, '42': 267, '43': 274, '44': 280, '45': 287, '46': 294, '47': 301, '48': 309, '49': 316, '50': 324,
    '51': 332, '52': 340, '53': 348, '54': 357, '55': 365, '56': 374, '57': 383, '58': 392, '59': 402, '60': 412,
    '61': 422, '62': 432, '63': 442, '64': 453, '65': 464, '66': 475, '67': 487, '68': 499, '69': 511, '70': 523,
    '71': 536, '72': 549, '73': 562, '74': 576, '75': 590, '76': 604, '77': 619, '78': 634, '79': 649, '80': 665,
    '81': 681, '82': 698, '83': 715, '84': 732, '85': 750, '86': 768, '87': 787, '88': 806, '89': 825, '90': 845,
    '91': 866, '92': 887, '93': 909, '94': 931, '95': 953, '96': 976,
}

REVERSE_EIA96_CODES = {v: k for k, v in EIA96_CODES.items()}

# Standard resistor series (E6, E12, E24) - base values
E6_SERIES = [1.0, 1.5, 2.2, 3.3, 4.7, 6.8]
E12_SERIES = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
E24_SERIES = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 
              3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]

def get_tolerance_for_smd_code(code: str) -> str:
    """Determines tolerance based on SMD code format"""
    if len(code) == 4 and code.isdigit():
        return "1%"  # 4-digit codes typically 1%
    elif len(code) == 3 and code[:2].isdigit() and code[2].isalpha():
        return "1%"  # EIA-96 codes are 1%
    elif len(code) == 3 and code.isdigit():
        return "5%"  # 3-digit codes typically 5%
    elif len(code) == 2 and code.isdigit():
        return "5%"  # 2-digit codes typically 5%
    else:
        return "5%"  # Default

def determine_resistor_series(value: float) -> str:
    """Determines which standard series (E6/E12/E24) the value belongs to"""
    # Normalize value to 1-10 range to check against standard series
    magnitude = 0
    normalized = value
    while normalized >= 10:
        normalized /= 10
        magnitude += 1
    while normalized < 1:
        normalized *= 10
        magnitude -= 1
    
    # Check if value is in E6 series (within 1% tolerance)
    for base in E6_SERIES:
        if abs(normalized - base) / base < 0.01:
            return "E6"
    
    # Check if value is in E12 series (within 1% tolerance) 
    for base in E12_SERIES:
        if abs(normalized - base) / base < 0.01:
            return "E12"
    
    # Check if value is in E24 series (within 1% tolerance)
    for base in E24_SERIES:
        if abs(normalized - base) / base < 0.01:
            return "E24"
    
    # If not in standard series, find closest E24 value
    return "E24"

def find_closest_e24_value(value: float) -> float:
    """Finds the closest E24 series value for a given resistance"""
    if value <= 0:
        return value
    
    # Find the appropriate decade multiplier
    magnitude = 0
    normalized = value
    while normalized >= 10:
        normalized /= 10
        magnitude += 1
    while normalized < 1:
        normalized *= 10
        magnitude -= 1
    
    # Find closest E24 value
    closest_base = min(E24_SERIES, key=lambda x: abs(x - normalized))
    
    # Scale back to original magnitude
    return closest_base * (10 ** magnitude)

def format_resistance(value: float, i18n=None, lang: str = 'en') -> str:
    """Formats the resistance value into a human-readable string (e.g., 10kΩ, 4.7Ω)."""
    if i18n:
        g_ohm = i18n.gettext("GΩ", locale=lang)
        m_ohm = i18n.gettext("MΩ", locale=lang)
        k_ohm = i18n.gettext("kΩ", locale=lang)
        ohm = i18n.gettext("Ω", locale=lang)
    else:
        g_ohm, m_ohm, k_ohm, ohm = "GΩ", "MΩ", "kΩ", "Ω"

    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.10g} {g_ohm}"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.10g} {m_ohm}"
    elif value >= 1_000:
        return f"{value / 1_000:.10g} {k_ohm}"
    return f"{value:.10g} {ohm}"


def smd_to_value(code: str) -> Union[float, None]:
    """
    Calculates the resistance from an SMD code.
    Supports 3-digit, 4-digit, R-notation, and EIA-96 codes.
    Returns resistance in ohms as a float, or None.
    """
    code = code.upper().strip()
    value = None

    # R-notation (e.g., 4R7 = 4.7Ω, R47 = 0.47Ω)
    if 'R' in code:
        try:
            parts = code.split('R')
            if len(parts) == 2:
                p1 = parts[0] if parts[0] else '0'
                p2 = parts[1] if parts[1] else ''
                value = float(f"{p1}.{p2}")
        except (ValueError, IndexError):
            return None

    # 2-digit code (e.g., 45 = 45Ω)
    elif len(code) == 2 and code.isdigit():
        value = int(code)

    # 3-digit code (e.g., 103 = 10 * 10^3 = 10kΩ)
    elif len(code) == 3 and code.isdigit():
        value = int(code[:2]) * (10 ** int(code[2]))

    # 4-digit code (e.g., 4702 = 470 * 10^2 = 47kΩ)
    elif len(code) == 4 and code.isdigit():
        value = int(code[:3]) * (10 ** int(code[3]))

    # EIA-96 code (e.g., 01A = 100 * 1 = 100Ω)
    elif len(code) == 3 and code[:2].isdigit() and code[2].isalpha():
        val_code = code[:2]
        mul_char = code[2]
        if val_code in EIA96_CODES and mul_char in EIA96_MULTIPLIERS:
            base_val = EIA96_CODES[val_code]
            multiplier = EIA96_MULTIPLIERS[mul_char]
            value = base_val * multiplier

    if value is not None:
        return float(value)

    return None


def parse_resistance_value(value_str: str) -> Union[float, None]:
    """Parses a string like '10k', '4.7M', '100', or '4R7' into a float value in Ohms."""
    value_str = value_str.upper().strip()
    value_str = value_str.replace("К", "K").replace("ОМ", "").strip()

    # Handle 'R' as a decimal point first
    if 'R' in value_str and '.' not in value_str:
        try:
            return float(value_str.replace('R', '.'))
        except ValueError:
            pass  # Will be handled by the logic below

    multiplier = 1
    if value_str.endswith('K'):
        multiplier = 1000
        value_str = value_str[:-1]
    elif value_str.endswith('M'):
        multiplier = 1_000_000
        value_str = value_str[:-1]
    elif value_str.endswith('G'):
        multiplier = 1_000_000_000
        value_str = value_str[:-1]

    try:
        # Allow for comma as decimal separator
        base_value = float(value_str.replace(',', '.'))
        return base_value * multiplier
    except ValueError:
        return None


def parse_smd_code(code: str) -> Optional[float]:
    code = code.lower()

    # EIA-96 format
    if len(code) == 3 and code[:2].isdigit() and code[2] in EIA96_MULTIPLIERS:
        value_code = code[:2]
        multiplier_char = code[2]
        if value_code in EIA96_CODES:
            base_value = EIA96_CODES[value_code]
            multiplier = EIA96_MULTIPLIERS[multiplier_char]
            return base_value * multiplier

    # Standard 3-digit or 4-digit format or with 'R'
    if 'r' in code:
        if 'r' in code:
            try:
                parts = code.split('r')
                if len(parts) == 2:
                    p1 = parts[0] if parts[0] else '0'
                    p2 = parts[1] if parts[1] else ''
                    value = float(f"{p1}.{p2}")
            except (ValueError, IndexError):
                return None

    # 3-digit code (e.g., 103 = 10 * 10^3 = 10kΩ)
    elif len(code) == 3 and code.isdigit():
        value = int(code[:2]) * (10 ** int(code[2]))

    # 4-digit code (e.g., 4702 = 470 * 10^2 = 47kΩ)
    elif len(code) == 4 and code.isdigit():
        value = int(code[:3]) * (10 ** int(code[3]))

    if value is not None:
        return float(value)

    return None


def find_closest_eia96_value(value: float) -> Optional[int]:
    """Finds the closest E96 series value for a given number."""
    if not REVERSE_EIA96_CODES:
        return None
    return min(REVERSE_EIA96_CODES.keys(), key=lambda x: abs(x - value))


def value_to_smd(value: float) -> dict[str, str]:
    """Converts a resistance value to its possible SMD codes."""
    if value <= 0:
        return {}

    codes = {}
    value_str = str(value)

    # Standard code
    if value < 1:
        smd_code = "R" + str(value).split('.')[1]
        codes['standard'] = smd_code.ljust(3, '0')
    elif value < 10 and '.' in value_str:
        smd_code = value_str.replace('.', 'R')
        codes['standard'] = smd_code
    else:
        significant_digits = "".join(filter(str.isdigit, value_str.split('.')[0]))
        if len(significant_digits) >= 2:
            if significant_digits[1] == '0' and len(significant_digits) > 2 and significant_digits[2] != '0':
                 # e.g., 105 -> 10, and then 5 zeroes
                num_zeros = len(significant_digits) - 2
                smd_code = f"{significant_digits[:2]}{num_zeros}"
            else:
                 num_zeros = len(str(int(value))) - len(significant_digits[:2]) if int(value) >=100 else 0
                 if int(value) >=10 :
                    num_zeros = len(str(int(value))) - 2
                    smd_code = f"{significant_digits[:2]}{num_zeros}"
                    codes['standard'] = smd_code
                 else: # 1 to 9 ohm
                     codes['standard'] = f"{int(value)}R0"



    # EIA-96 code
    if 10 <= value < 1000:  # EIA-96 is typically for values >= 10 Ohm
        # Find multiplier
        exponent = len(str(int(value))) - 1
        base_val = value / (10**exponent)

        closest_eia_val = find_closest_eia96_value(base_val * 100)
        if closest_eia_val:
            val_code = REVERSE_EIA96_CODES[closest_eia_val]
            # Find the multiplier character
            multiplier_char = next((k for k, v in EIA96_MULTIPLIERS.items() if v == 10**exponent), None)
            if multiplier_char:
                codes['eia96'] = f"{val_code}{multiplier_char.upper()}"

    return codes


# --- Color Code Calculator ---

COLOR_CODES = {
    # Color: (significant_figure, multiplier, tolerance_%, tcr_ppm/K)
    'black':  (0, 10**0, None, None),
    'brown':  (1, 10**1, 1, 100),
    'red':    (2, 10**2, 2, 50),
    'orange': (3, 10**3, None, 15),
    'yellow': (4, 10**4, None, 25),
    'green':  (5, 10**5, 0.5, 20),
    'blue':   (6, 10**6, 0.25, 10),
    'violet': (7, 10**7, 0.1, 5),
    'grey':   (8, 10**8, 0.05, 1),
    'white':  (9, 10**9, None, None),
    'gold':   (None, 10**-1, 5, None),
    'silver': (None, 10**-2, 10, None),
}

REVERSE_COLOR_CODES = {
    'figures': {v[0]: k for k, v in COLOR_CODES.items() if v[0] is not None},
    'multipliers': {v[1]: k for k, v in COLOR_CODES.items() if v[1] is not None},
    'tolerances': {v[2]: k for k, v in COLOR_CODES.items() if v[2] is not None}
}

BAND_OPTIONS = {
    'band1': ['brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white'],
    'band2': ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white'],
    'band3': ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white'], # For 5/6 band
    'multiplier': ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white', 'gold', 'silver'],
    'tolerance': ['brown', 'red', 'green', 'blue', 'violet', 'grey', 'gold', 'silver'],
    'tcr': ['brown', 'red', 'orange', 'yellow', 'blue', 'violet']
}


def calculate_resistance_from_colors(bands: list) -> Union[Tuple[float, Optional[float], Optional[int]], Tuple[None, None, None]]:
    """
    Calculates resistance, tolerance, and TCR from a list of color names.
    Supports 4, 5, and 6 band resistors.
    """
    num_bands = len(bands)
    
    if num_bands not in [4, 5, 6]:
        return None, None, None

    try:
        if num_bands == 4:
            # 2 digits, multiplier, tolerance
            digit1 = COLOR_CODES[bands[0]][0]
            digit2 = COLOR_CODES[bands[1]][0]
            multiplier = COLOR_CODES[bands[2]][1]
            tolerance = COLOR_CODES[bands[3]][2]
            tcr = None
            value = (digit1 * 10 + digit2) * multiplier

        elif num_bands == 5:
            # 3 digits, multiplier, tolerance
            digit1 = COLOR_CODES[bands[0]][0]
            digit2 = COLOR_CODES[bands[1]][0]
            digit3 = COLOR_CODES[bands[2]][0]
            multiplier = COLOR_CODES[bands[3]][1]
            tolerance = COLOR_CODES[bands[4]][2]
            tcr = None
            value = (digit1 * 100 + digit2 * 10 + digit3) * multiplier
        
        else: # 6 bands
            # 3 digits, multiplier, tolerance, TCR
            digit1 = COLOR_CODES[bands[0]][0]
            digit2 = COLOR_CODES[bands[1]][0]
            digit3 = COLOR_CODES[bands[2]][0]
            multiplier = COLOR_CODES[bands[3]][1]
            tolerance = COLOR_CODES[bands[4]][2]
            tcr = COLOR_CODES[bands[5]][3]
            value = (digit1 * 100 + digit2 * 10 + digit3) * multiplier

        tolerance_val = float(tolerance) if tolerance is not None else None
        return float(value), tolerance_val, tcr

    except (KeyError, TypeError, IndexError):
        # Invalid color or band configuration
        return None, None, None 

def value_to_colors(value: float, tolerance: float) -> Union[list[str], None]:
    """
    Finds the color bands for a given resistance value and tolerance.
    Prioritizes 4-band, then 5-band.
    """
    if value <= 0:
        return None

    s_value = str(value).replace('.', '')
    # Find the first non-zero digit
    first_digit_pos = -1
    for i, char in enumerate(str(value)):
        if char.isdigit() and char != '0':
            first_digit_pos = i
            break
            
    # Try 5-band resistor for high precision (3 significant digits)
    if tolerance in [1, 2, 0.5, 0.25, 0.1, 0.05]:
        if len(s_value) >= 3:
            try:
                digits_str = s_value[:3]
                val_part = int(digits_str)
                exp = len(str(int(value))) - 3 if '.' not in str(value) else first_digit_pos - 1
                multiplier = 10**exp
                
                digit1 = REVERSE_COLOR_CODES['figures'].get(int(digits_str[0]))
                digit2 = REVERSE_COLOR_CODES['figures'].get(int(digits_str[1]))
                digit3 = REVERSE_COLOR_CODES['figures'].get(int(digits_str[2]))
                mult_color = REVERSE_COLOR_CODES['multipliers'].get(multiplier)
                tol_color = REVERSE_COLOR_CODES['tolerances'].get(tolerance)
                if digit1 and digit2 and digit3 and mult_color and tol_color:
                    return [digit1, digit2, digit3, mult_color, tol_color]
            except (ValueError, IndexError):
                pass # Fallback to 4-band

    # Try 4-band resistor (2 significant digits)
    try:
        digits_str = s_value[:2]
        val_part = int(digits_str)
        exp = len(str(int(value))) - 2 if '.' not in str(value) else first_digit_pos
        multiplier = 10**exp
        
        digit1 = REVERSE_COLOR_CODES['figures'].get(int(digits_str[0]))
        digit2 = REVERSE_COLOR_CODES['figures'].get(int(digits_str[1]))
        mult_color = REVERSE_COLOR_CODES['multipliers'].get(multiplier)
        tol_color = REVERSE_COLOR_CODES['tolerances'].get(tolerance)
        if digit1 and digit2 and mult_color and tol_color:
            return [digit1, digit2, mult_color, tol_color]
    except (ValueError, IndexError):
        return None

    return None # No standard representation found 