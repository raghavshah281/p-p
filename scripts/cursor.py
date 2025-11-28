import requests
from bs4 import BeautifulSoup
import json
import re

def _clean_feature_text(text):
    """Helper to clean up raw feature text from HTML."""
    text = text.replace('✓', '').replace('<!-- -->', '').strip()
    # Capitalize first letter of each sentence, handle specific phrases
    if text.startswith("3x usage"):
        return "3x Usage on all OpenAI, Claude, Gemini models"
    if text.startswith("20x usage"):
        return "20x Usage on all OpenAI, Claude, Gemini models"
    if text.startswith("One-week Pro trial"):
        return "One-week Pro trial"
    if text.startswith("Unlimited reviews on up to"):
        return "Unlimited Code Reviews (up to 200 PRs/month)"
    if text.startswith("Unlimited code reviews on all PRs"):
        return "Unlimited Code Reviews on all PRs"
    return text[0].upper() + text[1:] if text else ""

def extract_cursor_pricing_features(html_source_code):
    """
    Extracts pricing and features information from Cursor's pricing page HTML
    source code and returns it as a JSON object with a structured format.
    """
    soup = BeautifulSoup(html_source_code, 'html.parser')
    plans_output = {}

    # Determine if "Monthly" or "Yearly" is selected by default
    monthly_checked = soup.find('input', {'name': 'frequency', 'value': 'monthly', 'checked': True}) is not None
    yearly_checked = soup.find('input', {'name': 'frequency', 'value': 'yearly', 'checked': True}) is not None

    # Process plan groups: Individual Plans, Business Plans, Bugbot Add-on
    plan_groups = soup.find_all('div', class_='space-y-v8/12') # This div typically wraps the H2 and the cards

    for group in plan_groups:
        group_title_element = group.find('h2')
        if not group_title_element:
            continue
        
        group_title = group_title_element.get_text(strip=True).replace(' Plans', '').replace(' Add-on', '') # Clean up title

        cards_container = group.find('div', class_='grid')
        if not cards_container:
            continue

        if "Bugbot" in group_title: # For Bugbot, we want a nested structure
            plans_output[group_title] = {}
            target_output_dict = plans_output[group_title]
        else:
            target_output_dict = plans_output # For Individual and Business, top-level keys

        for card in cards_container.find_all('a', class_='card--text'):
            plan_name = card.find('h3', class_='type-md').get_text(strip=True)
            
            base_pricing = {"Monthly Price (Billed Monthly)": "Not specified", "Yearly Price (Billed Annually)": "Not specified"}
            
            # Extract main price text (e.g., "$20", "Free", "Custom")
            price_element = card.find('p', class_='flex items-baseline').find('span', class_='type-md')
            raw_price_value = price_element.get_text(strip=True) if price_element else ""

            # Extract unit/frequency if present (e.g., "/mo.", "/user/mo.")
            unit_element = card.find('p', class_='flex items-baseline').find('span', class_='text-sm')
            price_unit = unit_element.get_text(strip=True).replace(' ', '') if unit_element else "" # Remove zero-width spaces

            # Construct full price string
            full_price_string = f"{raw_price_value}{price_unit}" if raw_price_value and price_unit else raw_price_value

            if "Free" in raw_price_value:
                base_pricing["Monthly Price (Billed Monthly)"] = "Free"
                base_pricing["Yearly Price (Billed Annually)"] = "Free"
            elif "Custom" in raw_price_value:
                base_pricing["Monthly Price (Billed Monthly)"] = "Custom"
                base_pricing["Yearly Price (Billed Annually)"] = "Custom"
            else:
                # Based on the provided HTML, 'monthly' is checked.
                # If we had access to both states, we'd adjust. For now, we assume the displayed is monthly.
                if monthly_checked:
                    base_pricing["Monthly Price (Billed Monthly)"] = full_price_string
                elif yearly_checked: # This branch won't be hit with the current static HTML
                    base_pricing["Yearly Price (Billed Annually)"] = full_price_string
                else: # Default if no specific toggle is found
                    base_pricing["Monthly Price (Billed Monthly)"] = full_price_string
            
            # Extract features
            features_list_elements = card.find('ul', role='list')
            features_dict = {}
            if features_list_elements:
                for li in features_list_elements.find_all('li'):
                    feature_text = _clean_feature_text(li.get_text(strip=True))
                    if feature_text:
                        features_dict[feature_text] = "Included"

            target_output_dict[plan_name] = {"Base Pricing": base_pricing, "Features": features_dict}

    return plans_output

def get_cursor_pricing_info(url="https://cursor.com/pricing"):
    """
    Fetches the HTML from the Cursor pricing URL and extracts information.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        html_source_code = response.text
        return extract_cursor_pricing_features(html_source_code)
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to retrieve URL {url}: {e}"}

if __name__ == "__main__":
    pricing_info = get_cursor_pricing_info("https://cursor.com/pricing")
    print(json.dumps(pricing_info, indent=4))
