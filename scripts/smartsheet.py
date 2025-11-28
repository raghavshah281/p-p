import requests
from bs4 import BeautifulSoup
import json
import re

def extract_smartsheet_pricing(url="https://www.smartsheet.com/pricing"):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not retrieve the webpage: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')

    restructured_pricing = {}

    # --- Extracting main pricing plans from the "plans" section ---
    pricing_plans_container = soup.find('div', class_='plans')
    if not pricing_plans_container:
        return {"error": "Could not find the main pricing plans container (div.plans)."}

    price_boxes = pricing_plans_container.find_all('div', class_='price-box')

    for box in price_boxes:
        plan_name_tag = box.find('h3', class_='header')
        if not plan_name_tag:
            continue
        plan_name = plan_name_tag.get_text(strip=True)

        # Standardize plan names for output keys
        # "Advanced Work Management" is a special case, it's a plan, not an add-on in the main grid
        output_plan_key = plan_name.replace(" ", "").replace("Smartsheet", "")
        if output_plan_key == "Pro":
            output_plan_key = "Pro" # Keep as is
        elif output_plan_key == "Business":
            output_plan_key = "Business" # Keep as is
        elif output_plan_key == "Enterprise":
            output_plan_key = "Enterprise" # Keep as is
        elif output_plan_key == "AdvancedWorkManagement":
            output_plan_key = "AdvancedWorkManagement" # Keep as is

        if output_plan_key not in restructured_pricing:
            restructured_pricing[output_plan_key] = {
                "Base Pricing": {
                    "Monthly Price (Billed Monthly)": "Not Available",
                    "Yearly Price (Billed Annually)": "Not Available"
                },
                "Features": {}
            }
        
        # Extract pricing for USD, which is the default in the provided HTML
        usd_price_wrapper = box.find('span', class_='currency USD prices__price')
        if usd_price_wrapper:
            # Monthly price
            monthly_price_tag = usd_price_wrapper.find('span', class_='monthly-price')
            if monthly_price_tag:
                monthly_amount = monthly_price_tag.get_text(strip=True).replace(',', '') # Remove thousands comma
                per_member_text = usd_price_wrapper.find('span', class_='value-price')
                per_member_suffix = per_member_text.get_text(strip=True) if per_member_text else ""
                
                # Check for "Custom pricing" in disclaimer if no direct price is found for Enterprise/AWM
                if plan_name in ["Enterprise", "Advanced Work Management"]:
                    monthly_price_string = "Custom pricing"
                else:
                    monthly_price_string = f"${monthly_amount} {per_member_suffix} (billed monthly)"
                
                restructured_pricing[output_plan_key]["Base Pricing"]["Monthly Price (Billed Monthly)"] = monthly_price_string

            # Annual price
            annual_price_tag = usd_price_wrapper.find('span', class_='annual-price')
            if annual_price_tag:
                annual_amount = annual_price_tag.get_text(strip=True).replace(',', '') # Remove thousands comma
                per_member_text = usd_price_wrapper.find('span', class_='value-price')
                per_member_suffix = per_member_text.get_text(strip=True) if per_member_text else ""

                if plan_name in ["Enterprise", "Advanced Work Management"]:
                    yearly_price_string = "Custom pricing"
                else:
                    yearly_price_string = f"${annual_amount} {per_member_suffix} (billed yearly)"
                restructured_pricing[output_plan_key]["Base Pricing"]["Yearly Price (Billed Annually)"] = yearly_price_string

        # Extract introductory features directly below the price box
        intro_features_list = box.find('div', class_='field-text-body')
        if intro_features_list:
            # First part is descriptive text
            description_paragraph = intro_features_list.find('p')
            if description_paragraph:
                restructured_pricing[output_plan_key]["Features"]["Plan Description"] = description_paragraph.get_text(strip=True)

            # Then the bulleted list of included features
            features_ul = intro_features_list.find('ul')
            if features_ul:
                for li in features_ul.find_all('li'):
                    feature_text = li.get_text(strip=True)
                    # Attempt to extract quantity/detail from text
                    match_quantity = re.match(r'(\d+|\w+)\s+(.+)', feature_text)
                    if match_quantity:
                        quantity = match_quantity.group(1)
                        feature_name = match_quantity.group(2).replace(' per month', '')
                        features = restructured_pricing[output_plan_key]["Features"]
                        if "automations per month" in feature_text.lower():
                            features["Automated triggers (monthly)"] = quantity
                        elif "attachment storage" in feature_text.lower():
                            features["Attachment Storage"] = quantity
                        elif "free Viewers" in feature_text.lower():
                            features["Viewers"] = quantity
                        elif "free Guests" in feature_text.lower():
                            features["Guests"] = quantity
                        else:
                            features[feature_name] = quantity
                    else:
                        feature_name = feature_text.replace(':', '').strip()
                        if feature_name.lower() == "unlimited free viewers":
                            restructured_pricing[output_plan_key]["Features"]["Viewers"] = "Unlimited"
                        elif feature_name.lower() == "unlimited free guests":
                            restructured_pricing[output_plan_key]["Features"]["Guests"] = "Unlimited"
                        else:
                            restructured_pricing[output_plan_key]["Features"][feature_name] = "Included"

    # --- Extracting detailed features from the comparison table ---
    comparison_table = soup.find('table', class_='comparison-table')
    if not comparison_table:
        print("Warning: Could not find the comparison table. Detailed features might be missing.")
        return restructured_pricing # Return what we have so far

    # Extract column headers for plans from thead
    header_row = comparison_table.find('thead').find('tr')
    plan_columns = []
    # Skip the first column (feature name)
    for th in header_row.find_all('th')[1:]:
        plan_p_tag = th.find('p', class_='size-4')
        if plan_p_tag:
            plan_columns.append(plan_p_tag.get_text(strip=True).replace(" ", "").replace("Smartsheet", ""))
        else:
            plan_columns.append("UnknownPlan") # Fallback

    # Iterate through table rows to get features
    # Each row is a feature, and each td corresponds to a plan
    for row in comparison_table.find('tbody').find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue

        feature_category_tag = row.find('h3') # Check if it's a category header
        if feature_category_tag:
            # We can optionally use these categories, but for Notion-like flat features, we just ignore.
            continue 

        feature_name_tag = cells[0].find('a', class_='tooltip') # Feature name is usually in the first cell
        if not feature_name_tag:
            feature_name_tag = cells[0] # Fallback if not a tooltip
        
        feature_name = feature_name_tag.get_text(strip=True)
        # Clean feature name
        feature_name = feature_name.replace(':', '').replace('\n', '').strip()

        # Iterate through feature values for each plan column
        for i, plan_col_key in enumerate(plan_columns):
            if i + 1 < len(cells): # Ensure there's a cell for this plan
                feature_value_raw = cells[i + 1].get_text(strip=True)
                
                # Standardize feature values
                feature_value = "Included"
                if feature_value_raw.lower() == 'x' or feature_value_raw.lower() == 'unlimited':
                    feature_value = "Unlimited" if feature_value_raw.lower() == 'unlimited' else "Included"
                elif feature_value_raw.lower() == '-' or feature_value_raw.lower() == 'not included':
                    feature_value = "Not Included"
                elif "Add-on" in feature_value_raw:
                    # Extract starting price if available, otherwise just "Add-on"
                    price_match = re.search(r'Starting at (.+)', feature_value_raw)
                    if price_match:
                        feature_value = f"Add-on ({price_match.group(1).strip()})"
                    else:
                        feature_value = "Add-on"
                else:
                    feature_value = feature_value_raw # Keep as is if specific value

                if plan_col_key in restructured_pricing:
                    restructured_pricing[plan_col_key]["Features"][feature_name] = feature_value

    # Handle the "Free" plan if it exists (Smartsheet explicitly states Pro is 1-10 Members, etc.
    # A "Free" plan would likely be handled separately or deduced from the descriptions.
    # The current HTML doesn't show a dedicated "Free" plan price box or column.
    # However, it does mention "Try for free". If a free tier needs to be represented,
    # it might need to be hardcoded or inferred from other parts of the text.
    # For now, I'll assume the explicit plans are Pro, Business, Enterprise, AWM.
    # If a Free plan should be included:
    # restructured_pricing["Free"] = {
    #     "Base Pricing": {"Monthly Price (Billed Monthly)": "$0 / member / month", "Yearly Price (Billed Annually)": "$0 / member / month"},
    #     "Features": {"Basic Sheets": "Included", "Basic reports": "Included", ...}
    # }

    # Smartsheet also has "Premium features" as add-ons, usually listed separately.
    # We can parse the "Premium features" section and attribute them as add-ons.
    premium_features_section = soup.find('div', class_='brick--type--floyd-feature-slider')
    if premium_features_section:
        feature_cards = premium_features_section.find_all('div', class_='pricing-card')
        for card in feature_cards:
            feature_title_tag = card.find('h4', class_='field__item')
            if not feature_title_tag:
                continue
            feature_title = feature_title_tag.get_text(strip=True)

            eligible_plans_tags = card.find_all('span', class_='vocabulary-pricing_plans')
            eligible_for = [span.get_text(strip=True) for span in eligible_plans_tags]
            
            # This is an add-on, so we add it to an "Add-ons" top-level key
            if "Add-ons" not in restructured_pricing:
                restructured_pricing["Add-ons"] = {}
            
            # Extract price if available in the details section (e.g., Dynamic View)
            details_div = card.find('div', class_='details')
            addon_price = "Contact Sales"
            if details_div:
                price_entity_tag = details_div.find('span', class_='price-entity')
                if price_entity_tag:
                    # Look for USD price specifically
                    usd_addon_price_tag = price_entity_tag.find('span', class_='currency USD prices__price')
                    if usd_addon_price_tag:
                        monthly_addon_price = usd_addon_price_tag.find('span', class_='monthly-price')
                        if monthly_addon_price:
                            amount = monthly_addon_price.get_text(strip=True)
                            suffix = usd_addon_price_tag.find('span', class_='value-price')
                            suffix_text = suffix.get_text(strip=True) if suffix else ""
                            addon_price = f"${amount}{suffix_text}" # e.g., $125/month
                            # Smartsheet's add-on pricing seems to be fixed for monthly/annual once it's an add-on
                            # We can refine this if needed, but for now, take the monthly
                
            restructured_pricing["Add-ons"][feature_title] = {
                "Eligible Plans": ", ".join(eligible_for),
                "Pricing (USD)": addon_price
            }
            description_text_tag = card.find('div', class_='field--name-wysiwyg')
            if description_text_tag:
                 restructured_pricing["Add-ons"][feature_title]["Description"] = description_text_tag.get_text(strip=True)

    return restructured_pricing

# URL of the Smartsheet pricing page
smartsheet_url = "https://www.smartsheet.com/pricing"
smartsheet_pricing_data = extract_smartsheet_pricing(smartsheet_url)

json_output = json.dumps(smartsheet_pricing_data, indent=4)
print(json_output)
