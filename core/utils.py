import locale

def format_inr(amount) -> str:
    """
    Formats an amount into Indian Rupee format (e.g., ₹1,00,000).
    """
    if amount is None:
        return "₹0"
        
    try:
        amount = float(amount)
        # Try setting the locale to Indian English for formatting
        locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
        formatted = locale.currency(amount, symbol=False, grouping=True)
        return f"₹{formatted}"
    except (locale.Error, ValueError, TypeError, Exception):
        # Fallback if locale is not available or amount is invalid
        try:
            s = str(int(float(amount or 0)))
        except:
            return "₹0"
            
        if len(s) > 3:
            # Indian numbering system: group last 3 digits, then every 2 digits
            last_three = s[-3:]
            other_digits = s[:-3]
            # split other_digits into groups of 2 from the end
            groups = []
            while other_digits:
                groups.insert(0, other_digits[-2:])
                other_digits = other_digits[:-2]
            formatted_others = ",".join(groups)
            return f"₹{formatted_others},{last_three}"
        return f"₹{s}"

def to_celsius(kelvin: float) -> str:
    """
    Converts Kelvin to Celsius string.
    """
    celsius = kelvin - 273.15
    return f"{celsius:.1f}°C"

def to_kilometers(meters: float) -> str:
    """
    Converts meters to kilometers string.
    """
    km = meters / 1000.0
    return f"{km:.2f} km"

def fahrenheit_to_celsius(fahrenheit: float) -> str:
    """
    Converts Fahrenheit to Celsius string.
    """
    celsius = (fahrenheit - 32) * 5.0/9.0
    return f"{celsius:.1f}°C"

# Fallback conversion rate
EUR_TO_INR_RATE = 90.0

def convert_eur_to_inr(eur_amount: float) -> float:
    """
    Converts EUR to INR using the hardcoded rate.
    """
    return eur_amount * EUR_TO_INR_RATE
