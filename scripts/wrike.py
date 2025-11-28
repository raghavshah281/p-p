import requests
from bs4 import BeautifulSoup
import json
import re

def extract_wrike_pricing(url="https://www.wrike.com/comparison-table/"):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not retrieve the webpage: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')

    restructured_pricing = {}

    # --- Step 1: Extract Plan Names and Base Pricing from the Sticky Header ---
    comparison_header = soup.find('website-comparison-header')
    if not comparison_header:
        return {"error": "Could not find the <website-comparison-header> component."}

    header_plan_items = comparison_header.find_all('div', class_='comparison-header__item')
    
    plan_names_order = [] 

    for item in header_plan_items:
        plan_title_tag = item.find('p', class_='comparison-header__title')
        if not plan_title_tag:
            continue
        plan_name = plan_title_tag.get_text(strip=True)
        plan_names_order.append(plan_name) 

        restructured_pricing[plan_name] = {
            "Base Pricing": {
                "Monthly Price (Billed Monthly)": "Not Available",
                "Yearly Price (Billed Annually)": "Not Available"
            },
            "Features": {}
        }
        
        price_block = item.find('section', class_='comparison-header__price-block')
        if price_block:
            price_amount_tag = price_block.find('h5', class_='comparison-header__price')
            price_desc_tag = price_block.find('div', class_='comparison-header__price-description')
            
            if price_amount_tag and price_desc_tag:
                amount = price_amount_tag.get_text(strip=True)
                description = price_desc_tag.get_text(strip=True)
                price_string = f"{amount} {description}"
                restructured_pricing[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = price_string
                restructured_pricing[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = price_string
            
        contact_button = item.find('button', string=re.compile(r'Contact us', re.IGNORECASE))
        if contact_button:
            restructured_pricing[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = "Custom Pricing (Contact Sales)"
            restructured_pricing[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = "Custom Pricing (Contact Sales)"

        if plan_name == "Free":
            restructured_pricing[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = "$0 user/ month"
            restructured_pricing[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = "$0 user/ month"

    # --- Step 2: Extract Detailed Features from all comparison tables ---
    main_comparison_widget = soup.find('website-pricing-comparison-table')
    if not main_comparison_widget:
        return {"error": "Could not find the main <website-pricing-comparison-table> component."}

    content_blocks = main_comparison_widget.find_all(['website-wysiwyg']) # Focus only on website-wysiwyg for categories and tables
    # Changed to only search for 'website-wysiwyg' directly, as other tags
    # might not consistently contain the structure we expect for categories/tables.
    # The categories and tables are consistently within 'website-wysiwyg' blocks in the provided HTML.
    
    current_category = "General"

    for block in content_blocks:
        table_element = None # Initialize table_element to None for each block iteration

        # Check for a category header within the current block
        category_header_div = block.find('div', class_='website-wysiwyg__content')
        if category_header_div:
            h6_tag = category_header_div.find('h6')
            if h6_tag:
                current_category = h6_tag.get_text(strip=True).replace("&amp;", "&").strip()
            
        # Find the table within this current 'website-wysiwyg' block.
        # It could be directly inside, or as a sibling within the same section.
        table_element = block.find('table', class_='website-table__wrap')
        if not table_element:
            # If not directly found, check if it's a sibling div containing the table
            next_table_container = block.find_next_sibling('div', class_='website-wysiwyg__table-with-spacings')
            if next_table_container:
                table_element = next_table_container.find('table', class_='website-table__wrap')

        if not table_element:
            continue # No table found for this block, continue to next block

        table_rows = table_element.find('tbody').find_all('tr', class_='website-table__row')
        if not table_rows:
            continue
        
        header_cells = table_rows[0].find_all('td')
        if not header_cells:
            continue
        
        table_specific_plan_columns = [cell.get_text(strip=True) for cell in header_cells[1:]]

        for row in table_rows[1:]:
            cells = row.find_all('td')
            if not cells:
                continue
            
            feature_name_cell = cells[0]
            feature_name_raw = feature_name_cell.get_text(separator=" ", strip=True)
            
            feature_name = re.sub(r'\s*\([^)]*\)', '', feature_name_raw).strip()
            feature_name = feature_name.replace(':', '').replace('\n', '').strip()
            
            if not feature_name or feature_name.lower().startswith("ai essentials") or feature_name.lower().startswith("ai elite"):
                continue

            for col_idx, plan_col_name in enumerate(table_specific_plan_columns):
                plan_output_key = plan_col_name
                
                if plan_output_key not in restructured_pricing:
                    restructured_pricing[plan_output_key] = {"Base Pricing": {}, "Features": {}}
                
                feature_value_cell = cells[col_idx + 1]

                value = ""
                if 'icon_green_checked.svg' in str(feature_value_cell):
                    value = "Included"
                elif '–' == feature_value_cell.get_text(strip=True):
                    value = "Not Included"
                else:
                    value = feature_value_cell.get_text(strip=True)
                    value = BeautifulSoup(value, 'html.parser').get_text(strip=True).replace('\n', ' ')
                    if value == '':
                        value = "Not Included"

                feature_key = f"{current_category.replace(':', '')}: {feature_name}"
                restructured_pricing[plan_output_key]["Features"][feature_key] = value

    # --- Final Cleanup ---
    plans_to_remove = []
    for plan_name, data in restructured_pricing.items():
        if plan_name == "Add-ons":
            continue
        if not data["Base Pricing"].get("Monthly Price (Billed Monthly)") and not data["Base Pricing"].get("Yearly Price (Billed Annually)"):
            del data["Base Pricing"]
        
        if not data["Features"]:
            del data["Features"]

        if not data.get("Base Pricing") and not data.get("Features"):
            plans_to_remove.append(plan_name)
    
    for plan_name in plans_to_remove:
        del restructured_pricing[plan_name]

    return restructured_pricing

# URL of the Wrike pricing comparison table
wrike_url = "https://www.wrike.com/comparison-table/"
wrike_pricing_data = extract_wrike_pricing(wrike_url)

json_output = json.dumps(wrike_pricing_data, indent=4)
print(json_output)
