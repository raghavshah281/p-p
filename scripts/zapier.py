import requests
from bs4 import BeautifulSoup
import json

def extract_zapier_pricing(url="https://zapier.com/pricing"):
    """
    Extracts pricing and features information from Zapier's pricing page.

    Args:
        url (str): The URL of Zapier's pricing page.

    Returns:
        str: A JSON string containing the extracted pricing and features,
             or an error message if the extraction fails.
    """
    try:
        # 1. Fetch the content of the URL
        response = requests.get(url, timeout=10) # Added a timeout for robustness
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        html_content = response.text

        # 2. Parse the HTML content using Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')

        pricing_data = []

        # Find the main container for the pricing plans for the "Platform" tab
        # Based on the provided HTML, these seem to be inside a div with a specific class that
        # indicates a grid layout for plan cards. We'll look for a common pattern.
        # The class 'css-1gq79n2' seems to be a stable container for the plan cards.
        main_pricing_section = soup.find('div', class_=lambda x: x and 'css-1gq79n2' in x)

        if not main_pricing_section:
            print("Warning: Could not find the main pricing section container (css-1gq79n2). "
                  "Website structure might have changed.")
            # Attempt a fallback for a more general grid or flex container for plans
            main_pricing_section = soup.find('div', class_=lambda x: x and 'grid' in x and 'gap' in x)

        if not main_pricing_section:
             return json.dumps({"error": "No main pricing section found to extract plans from. "
                                         "The website structure might have changed significantly."}, indent=4)


        # Find individual plan cards. They seem to be wrapped in a div with a dynamic class
        # that contains 'PlanCard-PlanCard__tableFeatureRoot'.
        plan_cards = main_pricing_section.find_all('div', class_=lambda x: x and 'PlanCard-PlanCard__tableFeatureRoot' in x)

        if not plan_cards:
            print("Warning: No individual plan cards found within the main section. "
                  "Please inspect the page's HTML to find the correct class for plan containers.")
            return json.dumps({"error": "No pricing plans could be extracted. "
                                        "The website structure might have changed, "
                                        "or the selectors are incorrect."}, indent=4)

        for card in plan_cards:
            plan = {}

            # Extract Plan Name
            # The plan name is usually in an <h2> tag with a class containing 'PlanCard__planTitle'
            title_tag = card.find('h2', class_=lambda x: x and 'PlanCard__planTitle' in x)
            plan['name'] = title_tag.get_text(strip=True) if title_tag else "Unknown Plan"

            # Extract Description
            # The description is often in a <p> tag with a class containing 'PlanCard__planDescription'
            description_tag = card.find('p', class_=lambda x: x and 'PlanCard__planDescription' in x)
            plan['description'] = description_tag.get_text(strip=True) if description_tag else "No description found"

            # Extract Price
            # The price is in a span with a class containing 'css-1nu16jl' (e.g., "$0" or "$19.99")
            # And the frequency (e.g., "/mo") is in a span with a class containing 'css-1mvbr4t'
            price_main_tag = card.find('span', class_=lambda x: x and 'css-1nu16jl' in x)
            price_freq_tag = card.find('span', class_=lambda x: x and 'css-1mvbr4t' in x)
            price_billed_annually_tag = card.find('div', class_=lambda x: x and 'css-14i0g9c' in x) # "Free forever" or "Billed annually"
            
            full_price_text = ""
            if price_main_tag:
                full_price_text += price_main_tag.get_text(strip=True)
            if price_freq_tag:
                full_price_text += price_freq_tag.get_text(strip=True)
            
            if full_price_text:
                plan['price'] = full_price_text
            else:
                # Fallback for "Contact for pricing" if price_main_tag is not found
                contact_pricing_tag = card.find('div', class_=lambda x: x and 'css-nslgl' in x) # for Enterprise plan
                if contact_pricing_tag:
                    plan['price'] = contact_pricing_tag.get_text(strip=True)
                else:
                    plan['price'] = "Price not found"

            # Billing details (e.g., "Free forever", "Billed annually")
            if price_billed_annually_tag and price_billed_annually_tag.get_text(strip=True) != "":
                plan['billing_details'] = price_billed_annually_tag.get_text(strip=True)
            elif 'contact for pricing' not in plan['price'].lower(): # If it's not enterprise, default to monthly if price says /mo
                if '/mo' in plan['price'] and 'billed annually' not in plan.get('billing_details', '').lower():
                    plan['billing_details'] = "Billed monthly"
            else:
                plan['billing_details'] = ""


            # Extract Features
            features = []
            # Features are grouped under a <p> tag with class 'PlanCard__featureTitle'
            # and then individual features are in divs with class 'css-1e1ggoi'
            features_section = card.find('div', class_=lambda x: x and 'PlanCard__featuresWrapper' in x)
            if features_section:
                feature_group_title_tag = features_section.find('p', class_=lambda x: x and 'PlanCard__featureTitle' in x)
                if feature_group_title_tag:
                    features.append(feature_group_title_tag.get_text(strip=True))

                for feature_item in features_section.find_all('div', class_=lambda x: x and 'css-1e1ggoi' in x):
                    # The actual feature text is inside a div with class 'css-7mtdph'
                    feature_text_container = feature_item.find('div', class_=lambda x: x and 'css-7mtdph' in x)
                    if feature_text_container:
                        feature_text = feature_text_container.get_text(strip=True)
                        # Clean up the text by removing redundant tooltip icons' text content
                        # This specifically targets cases like "Zapier automation platformZapier automation platform"
                        feature_text = feature_text.replace('Zapier automation platformZapier automation platform', 'Zapier automation platform')
                        features.append(feature_text)
            
            plan['features'] = [f for f in features if f] # Filter out any empty strings
            pricing_data.append(plan)

        return json.dumps(pricing_data, indent=4)

    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Network or HTTP error: {e}"}, indent=4)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred during parsing: {e}"}, indent=4)

# --- Main execution ---
if __name__ == "__main__":
    zapier_pricing_url = "https://zapier.com/pricing"
    json_output = extract_zapier_pricing(zapier_pricing_url)
    print(json_output)
