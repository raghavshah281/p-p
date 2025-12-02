import requests
from bs4 import BeautifulSoup
import json
import re

def extract_pricing_only(url="https://n8n.io/pricing/"):
    """
    Fetches the HTML source code from the given URL and extracts 
    ONLY the plan names and pricing information.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        html_source_code = response.text
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to retrieve URL {url}: {e}"}

    soup = BeautifulSoup(html_source_code, 'html.parser')
    plans_data = []

    # Find the main pricing cards
    pricing_cards = soup.find_all('div', class_=lambda x: x and 'pricing-plan' in x)

    if not pricing_cards:
        return {"error": "Could not find pricing plan cards in the provided HTML."}

    for card in pricing_cards:
        plan = {}

        # --- 1. Extract Plan Name ---
        name_element = card.find('h3', class_=lambda x: x and ('title' in x and 'title--white' in x))
        if name_element:
            plan['name'] = name_element.get_text(strip=True)
        else:
            # Fallback for name
            name_element_fallback = card.find(['h2', 'h3', 'strong'])
            if name_element_fallback:
                plan['name'] = name_element_fallback.get_text(strip=True)
            else:
                continue # Skip if we can't identify a plan name

        # --- 2. Extract Pricing ---
        # Initialize pricing as None
        price_text_cleaned = None

        # Attempt to find the standard numerical price class (e.g., "20€")
        price_main_element = card.find('div', class_=lambda x: x and 'text-headline-md' in x)
        
        if price_main_element:
            # Get text, replace newlines with spaces to handle "20€ /mo" formatting
            raw_text = price_main_element.get_text(separator=" ", strip=True)
            price_text_cleaned = " ".join(raw_text.split()) # Removes extra whitespace
        else:
            # Handle "Contact Sales" or "Enterprise" buttons if no price number exists
            contact_us_element = card.find(text=re.compile(r'Contact sales', re.IGNORECASE))
            if contact_us_element:
                price_text_cleaned = "Contact Sales"
            else:
                # Handle "Free" or "Trial" specific text
                free_trial_text = card.find(text=re.compile(r'Start free trial', re.IGNORECASE))
                if free_trial_text:
                    # Check if there is a workflow execution tier associated with the price
                    # (e.g. "Starter" isn't free, but has a trial, so we look for the sub-text)
                    execution_value_element = card.find('p', class_=lambda x: x and 'text-xxl' in x)
                    if execution_value_element:
                        # Extract "2.5k workflow executions"
                        val = execution_value_element.get_text(strip=True)
                        price_text_cleaned = f"Starts at {val} executions (Free trial available)"
                    else:
                        price_text_cleaned = "Free trial available"

        # Final fallback
        if not price_text_cleaned:
            price_text_cleaned = "Not specified"

        plan['price'] = price_text_cleaned
        
        plans_data.append(plan)

    return {"n8n_plans": plans_data}

if __name__ == "__main__":
    pricing_info = extract_pricing_only("https://n8n.io/pricing/")
    print(json.dumps(pricing_info, indent=4))
