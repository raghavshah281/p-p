import requests
from bs4 import BeautifulSoup
import json
import re

def clean_text(text):
    """Clean whitespace and newlines."""
    if not text:
        return ""
    return ' '.join(text.split())

def get_check_value(cell):
    """
    Analyzes a table cell to see if it contains a Green Check (Included), 
    Red Cross (Not Included), or text.
    """
    # Check for specific icon classes used in Webflow
    if cell.find('div', class_='is-green'):
        return "Included"
    elif cell.find('div', class_='is-red'):
        return "Not Included"
    
    # If no icons, get text
    text = clean_text(cell.get_text())
    return text if text else "Not Included"

def extract_pricing_data(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Use an ordered list to map table columns to plans
        # Based on the HTML visual order: Free -> Pro -> Team -> Enterprise
        plan_names = ["Free", "Pro", "Team", "Enterprise"]
        
        # Initialize Output Dictionary
        output = {
            plan: {
                "Base Pricing": {
                    "Monthly Price (Billed Monthly)": "Contact Sales",
                    "Yearly Price (Billed Annually)": "Contact Sales"
                },
                "Features": {}
            } 
            for plan in plan_names
        }

        # -------------------------------------------------------
        # 1. Extract Base Pricing & Limits from Top Cards
        # -------------------------------------------------------
        # We target the specific new pricing cards
        cards = soup.find_all('div', class_='pricing_plan_new')
        
        # We assume the cards appear in the same order as our plan_names list
        for i, card in enumerate(cards):
            if i >= len(plan_names): break
            
            plan_key = plan_names[i]
            
            # --- Extract Annual Price ---
            annual_wrapper = card.find('div', class_='pricing-wrapper-annual')
            if annual_wrapper:
                amount_div = annual_wrapper.find('div', class_='is-amount')
                amount = clean_text(amount_div.text) if amount_div else "Custom"
                
                # Check if it's a number or text
                if any(char.isdigit() for char in amount):
                    price_str = f"${amount} / month (billed annually)"
                else:
                    price_str = amount # e.g. "Custom"
                
                output[plan_key]["Base Pricing"]["Yearly Price (Billed Annually)"] = price_str

                # Extract Annual Specific Features (Actions/Credits often differ by term)
                # The actions component is usually the next sibling
                actions_block = annual_wrapper.find_next_sibling('div', class_='actions_component')
                if actions_block:
                    items = actions_block.find_all('div', class_='actions_item')
                    for item in items:
                        val = clean_text(item.get_text())
                        if val:
                            output[plan_key]["Features"][f"Annual Limits"] = output[plan_key]["Features"].get(f"Annual Limits", "") + f" {val} |"

            # --- Extract Monthly Price ---
            monthly_wrapper = card.find('div', class_='pricing-wrapper-monthly')
            if monthly_wrapper:
                amount_div = monthly_wrapper.find('div', class_='is-amount')
                amount = clean_text(amount_div.text) if amount_div else "Custom"
                
                if any(char.isdigit() for char in amount):
                    price_str = f"${amount} / month (billed monthly)"
                else:
                    price_str = amount

                output[plan_key]["Base Pricing"]["Monthly Price (Billed Monthly)"] = price_str
                
                # Extract Monthly Specific Features
                actions_block = monthly_wrapper.find_next_sibling('div', class_='actions_component')
                if actions_block:
                    items = actions_block.find_all('div', class_='actions_item')
                    for item in items:
                        val = clean_text(item.get_text())
                        if val:
                            output[plan_key]["Features"][f"Monthly Limits"] = output[plan_key]["Features"].get(f"Monthly Limits", "") + f" {val} |"

            # Clean up trailing pipes in limits
            if "Annual Limits" in output[plan_key]["Features"]:
                output[plan_key]["Features"]["Annual Limits"] = output[plan_key]["Features"]["Annual Limits"].strip(" |")
            if "Monthly Limits" in output[plan_key]["Features"]:
                output[plan_key]["Features"]["Monthly Limits"] = output[plan_key]["Features"]["Monthly Limits"].strip(" |")

        # -------------------------------------------------------
        # 2. Extract Detailed Features from Comparison Table
        # -------------------------------------------------------
        # This table contains the specific "Included/Not Included" data
        table_rows = soup.find_all('div', class_='comparison11_row')

        for row in table_rows:
            # Skip hidden rows (mobile views) or header rows
            classes = row.get('class', [])
            if 'hide' in classes or 'is-header' in classes:
                continue

            # Get Feature Name
            # Usually in a div with class 'comparison11_feature'
            feature_node = row.find('div', class_='comparison11_feature')
            if not feature_node: continue
            
            # Check for tooltip text first, fallback to direct text
            tooltip = feature_node.find('div', class_='feature_tooltip')
            feature_name = clean_text(tooltip.text) if tooltip else clean_text(feature_node.text)
            
            if not feature_name: continue

            # Get Values (There should be 4 content cells for Free, Pro, Team, Enterprise)
            cells = row.find_all('div', class_='comparison11_row-content')
            
            for idx, cell in enumerate(cells):
                if idx < len(plan_names):
                    plan_key = plan_names[idx]
                    feature_value = get_check_value(cell)
                    
                    # Add to features dict
                    output[plan_key]["Features"][feature_name] = feature_value

        # -------------------------------------------------------
        # 3. Extract Add-ons
        # -------------------------------------------------------
        add_ons = {}
        # Locate the specific grid for Top-ups
        top_up_grid = soup.find('div', class_=lambda x: x and 'pricing20_grid-list' in x and 'is-topups' in x)
        
        if top_up_grid:
            top_up_items = top_up_grid.find_all('div', class_='pricing20_plan')
            for item in top_up_items:
                name_div = item.find('div', class_='heading-style-h6')
                price_div = item.find('div', class_='heading-style-h4') # or h3
                unit_div = item.find('div', class_='text-color-secondary')

                if name_div and price_div:
                    name = clean_text(name_div.text)
                    price = clean_text(price_div.text)
                    unit = clean_text(unit_div.text) if unit_div else ""
                    
                    add_ons[name] = {
                        "Price": f"{price} {unit}".strip()
                    }

        # Add add-ons to final output
        final_output = output
        final_output["Add-ons"] = add_ons

        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

if __name__ == "__main__":
    target_url = "https://relevanceai.com/pricing"
    print(extract_pricing_data(target_url))
