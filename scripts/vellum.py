import requests
from bs4 import BeautifulSoup
import json
import re

def clean_text(text):
    """Helper to clean whitespace and newlines."""
    if not text:
        return ""
    return ' '.join(text.split())

def analyze_cell(cell):
    """
    Analyzes a table cell in Vellum's pricing table.
    Returns 'Included', 'Not Included', or specific text.
    """
    # 1. Check for Text
    text_div = cell.find('div', class_='u-text-medium')
    if text_div:
        text_content = clean_text(text_div.text)
        if text_content:
            # Handle specific unicode or symbols like infinity
            if "∞" in text_content:
                return "Unlimited"
            return text_content

    # 2. Check for SVG Icon (The purple checkmark class in Vellum's CSS)
    # Vellum uses 'pricing_grid_icon' class for checkmarks
    icon = cell.find('svg', class_='pricing_grid_icon')
    if icon:
        return "Included"

    # 3. Check for Image Icon (Used in Enterprise column sometimes)
    img_icon = cell.find('img', class_='pricing_icon')
    if img_icon:
        return "Included"

    return "Not Included"

def extract_vellum_pricing(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Define Plan Order based on visual layout of the page
        plan_names = ["Free", "Pro", "Business", "Enterprise"]
        
        output_data = {
            plan: {
                "Base Pricing": "Custom", 
                "Description": "",
                "Features": {}
            }
            for plan in plan_names
        }

        # ---------------------------------------------------------
        # PART 1: Extract Pricing Cards (Top Section)
        # ---------------------------------------------------------
        # Vellum uses class 'pricng_card' (note the typo in their source)
        cards = soup.find_all('div', class_='pricng_card')

        for i, card in enumerate(cards):
            if i >= len(plan_names): break
            plan_name = plan_names[i]

            # Extract Description
            desc_tag = card.find('p', class_='u-text-medium')
            if desc_tag:
                output_data[plan_name]["Description"] = clean_text(desc_tag.text)

            # Extract Price
            price_large = card.find('div', class_='u-text-large')
            price_regular = card.find('div', class_='u-text-regular')
            
            if price_large:
                amount = clean_text(price_large.text)
                period = clean_text(price_regular.text) if price_regular else ""
                
                full_price = f"{amount} {period}".strip()
                output_data[plan_name]["Base Pricing"] = full_price

            # Extract Top-level Features (inside the card)
            features_block = card.find('div', class_='pricing_features')
            if features_block:
                feature_rows = features_block.find_all('div', class_='u-hflex-left-center')
                for row in feature_rows:
                    feature_text = clean_text(row.text)
                    if feature_text:
                        # Add as a "Highlighted Feature" to distinguish from table data
                        output_data[plan_name]["Features"][f"Highlight: {feature_text}"] = "Included"

        # ---------------------------------------------------------
        # PART 2: Extract Comparison Table (Grid)
        # ---------------------------------------------------------
        # Vellum uses div rows with class 'pricing_line'
        # We skip rows that contain 'is--header' (category headers or main header)
        
        rows = soup.find_all('div', class_='pricing_line')

        for row in rows:
            classes = row.get('class', [])
            
            # If it's the main header containing plan names, skip
            if 'is-main' in classes:
                continue
                
            # Check if it is a Category Header (e.g., "Features", "App Integrations")
            # In Vellum source, category headers usually have 'is--header' but NO data columns
            if 'is--header' in classes:
                # Determine if this is a sub-header or just a spacer. 
                # If it only has one child text block, it's a category.
                # For JSON simplicity, we will treat the row text as part of the feature name
                # or skip if strictly structural.
                # Based on provided HTML, 'is--header' rows often contain the Feature Name for the *next* section
                # or imply a category. Let's check if it has data cells.
                cols = row.find_all('div', class_='u-hflex-center-center')
                if not cols: 
                    continue # It's just a section header like "Deployments"

            # Extract Feature Name (First column)
            # Usually in a div with 'u-hflex-left-center'
            feature_name_col = row.find('div', class_='u-hflex-left-center')
            if not feature_name_col: continue

            # Get Text (check for tooltip wrapper inside)
            feature_name = clean_text(feature_name_col.text)
            
            # Clean up tooltip text if it got merged (e.g. "UsersInfo")
            # Vellum tooltips are usually separate divs, but beautifulsoup .text gets all.
            # We will just use the cleaned text.

            if not feature_name: continue

            # Extract Data Cells
            # Cells have class 'u-hflex-center-center gap-icon'
            cells = row.find_all('div', class_='u-hflex-center-center')

            # Map cells to plans
            for idx, cell in enumerate(cells):
                if idx < len(plan_names):
                    plan_key = plan_names[idx]
                    value = analyze_cell(cell)
                    
                    # Only add if relevant (ignore empty string results if any)
                    if value:
                        output_data[plan_key]["Features"][feature_name] = value

        # ---------------------------------------------------------
        # PART 3: Enterprise Specific Section
        # ---------------------------------------------------------
        # Vellum has a specific list for Enterprise features at the bottom
        # Class: 'enteprise-line' (Typo in source: enteprise vs enterprise)
        enterprise_rows = soup.find_all('div', class_='enteprise-line')
        
        for row in enterprise_rows:
            # Left side is feature name, right side is description
            cols = row.find_all('div', class_='u-hflex-left-center')
            if len(cols) >= 1:
                feat_name = clean_text(cols[0].text)
                feat_desc = clean_text(cols[1].text) if len(cols) > 1 else "Included"
                
                if feat_name:
                    output_data["Enterprise"]["Features"][feat_name] = feat_desc

        # ---------------------------------------------------------
        # Formatting Output
        # ---------------------------------------------------------
        final_output = {
            "source": url,
            "plans": output_data
        }

        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

# Execute
if __name__ == "__main__":
    target_url = "https://www.vellum.ai/pricing?utm_source=google&utm_medium=organic"
    print(extract_vellum_pricing(target_url))
