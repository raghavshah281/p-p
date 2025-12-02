import requests
from bs4 import BeautifulSoup
import json
import re

def clean_text(text):
    """Helper to clean whitespace and newlines."""
    if not text:
        return ""
    return ' '.join(text.split())

def calculate_yearly_price(monthly_price_str):
    """
    Calculates yearly price based on monthly string.
    Gumloop offers 20% off for annual billing.
    Input: "$37" -> Output: "$29.60 / month (billed annually)"
    """
    # Extract number
    match = re.search(r'\$(\d+)', monthly_price_str)
    if match:
        monthly_cost = int(match.group(1))
        # Apply 20% discount logic seen in source code "20% OFF"
        discounted_monthly = monthly_cost * 0.8 
        # Format: remove decimals if whole number
        if discounted_monthly.is_integer():
            discounted_monthly = int(discounted_monthly)
        else:
            discounted_monthly = f"{discounted_monthly:.2f}"
            
        return f"${discounted_monthly} / month (billed annually)"
    
    return "Custom"

def get_cell_value(cell):
    """
    Analyzes a table cell to determine its value.
    """
    # 1. Check for explicit text first
    text_content = clean_text(cell.get_text())
    if text_content and len(text_content) > 0:
        return text_content

    # 2. Check for SVG Icons
    svg = cell.find('svg')
    if svg:
        classes = svg.get('class', [])
        class_str = " ".join(classes) if classes else ""
        
        if 'lucide-check' in class_str or 'text-success-foreground' in class_str:
            return "Included"
        if 'lucide-minus' in class_str:
            return "Not Included"
            
    return "Not Included"

def extract_gumloop_pricing(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Final Output Dictionary
        output_data = {}

        table = soup.find('table')
        if not table:
            return json.dumps({"error": "Table not found"}, indent=4)

        # --- 1. Extract Plan Headers ---
        thead = table.find('thead')
        header_cols = thead.find_all('th')
        
        plan_map = {} # index -> plan_name

        for i in range(1, len(header_cols)):
            th = header_cols[i]
            name_span = th.find('span', class_='font-medium')
            price_span = th.find('span', class_='text-muted-foreground')
            
            if name_span:
                plan_name = clean_text(name_span.text)
                
                # Extract base monthly price string (e.g. "$37")
                raw_price_text = clean_text(price_span.text) if price_span else "Custom"
                
                # Determine Monthly & Yearly Prices
                if "Free" in plan_name:
                    monthly_price = "$0 / month"
                    yearly_price = "$0 / month"
                elif "Custom" in raw_price_text:
                    monthly_price = "Custom"
                    yearly_price = "Custom"
                else:
                    # Extract just the number part for calculation (e.g. "Starts at $37 / month" -> "$37")
                    price_match = re.search(r'\$\d+', raw_price_text)
                    base_price_str = price_match.group(0) if price_match else "Custom"
                    
                    monthly_price = f"{base_price_str} / month (billed monthly)"
                    yearly_price = calculate_yearly_price(base_price_str)

                # Initialize Plan Object in Output
                output_data[plan_name] = {
                    "Base Pricing": {
                        "Monthly Price (Billed Monthly)": monthly_price,
                        "Yearly Price (Billed Annually)": yearly_price
                    },
                    "Features": {}
                }
                
                plan_map[i] = plan_name

        # --- 2. Extract Features ---
        tbody = table.find('tbody')
        rows = tbody.find_all('tr')
        current_category = "General"

        for row in rows:
            # Category Header Check
            first_cell = row.find('td')
            if first_cell and first_cell.has_attr('colspan') and first_cell['colspan'] == '5':
                cat_text = clean_text(first_cell.get_text())
                if cat_text: current_category = cat_text
                continue

            # Data Row Check
            cells = row.find_all('td')
            if len(cells) < 2: continue

            feature_name = clean_text(cells[0].get_text())
            
            for i in range(1, len(cells)):
                if i in plan_map:
                    plan_name = plan_map[i]
                    value = get_cell_value(cells[i])
                    
                    # Create flattened feature name "Category - Feature" just like example
                    # But example shows nested features under "Features" key, without category prefix in key
                    # However, to match your previous specific request structure: "Features - Triggers"
                    
                    # If we strictly follow the "Notion" example provided in the prompt:
                    # The example uses simple keys like "Pages & blocks": "Unlimited"
                    # It does NOT prefix category.
                    # BUT, your previous output validation accepted "Features - Triggers". 
                    # I will stick to the flat keys (simple feature name) to match the Notion JSON structure example better
                    # UNLESS duplicates exist.
                    
                    # Using Simple Feature Name to match Notion example structure
                    output_data[plan_name]["Features"][feature_name] = value

        # Add specific Add-ons if extracted (not present in this specific HTML table, adding placeholders or logic if needed)
        # Since the HTML provided doesn't have a clear "Add-ons" section like the Notion example, we omit or leave empty.
        
        return json.dumps(output_data, indent=4)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

if __name__ == "__main__":
    target_url = "https://www.gumloop.com/pricing"
    print(extract_gumloop_pricing(target_url))
