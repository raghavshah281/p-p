import requests
from bs4 import BeautifulSoup
import json
import re # Import the regular expression module

def extract_asana_pricing_and_features_formatted(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html_content = response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None

    soup = BeautifulSoup(html_content, 'html.parser')

    formatted_pricing_data = {}

    plan_cards = soup.find_all('div', class_='css-cs6pme e13cy96x15')

    for card in plan_cards:
        plan_name_element = card.find('h3', class_='css-q480fw e13cy96x13')
        plan_name = plan_name_element.get_text(strip=True) if plan_name_element else "N/A"
        
        # We will use the raw plan_name for the top-level key as it's cleaner in this case
        plan_name_key = plan_name.strip()

        price_element = card.find('span', class_='css-yedtkm e13cy96x11')
        price = price_element.get_text(strip=True) if price_element else "N/A"

        price_period_element = card.find('p', class_='css-mmnhmq e13cy96x10')
        price_period = price_period_element.get_text(strip=True) if price_period_element else ""
        
        # Correctly use full_price_string
        full_price_description = f"{price} {price_period}".strip()

        features_dict = {}
        features_container = card.find('div', class_='css-wvvjt6 e13cy96x5')
        if features_container:
            # The first <p> element often describes the features that follow
            intro_p = features_container.find('p', class_='css-1c3p4lb e13cy96x4')
            if intro_p:
                features_dict["Introduction"] = intro_p.get_text(strip=True)

            for feature_item in features_container.find_all('li', class_='css-dubj1h e13cy96x2'):
                feature_text_element = feature_item.find('p')
                if feature_text_element:
                    feature_name = feature_text_element.get_text(strip=True)
                    feature_value = "Included" # Default value if no specific value is provided
                    
                    # Check for specific numerical/quantity values in the feature name
                    if "users" in feature_name.lower() or "mb max per file" in feature_name.lower():
                        value_match = re.search(r'(\d+\+?|Unlimited|\d+MB|\d+/\d+) (users|max per file)', feature_name, re.IGNORECASE)
                        if value_match:
                            feature_value = value_match.group(0)
                        else: # Fallback if regex doesn't match perfectly, use full text
                            feature_value = feature_name
                        feature_name = feature_name.split(' - ')[0].strip() # Clean name for key

                    # Check for links within the feature text for value
                    link_element = feature_text_element.find('a')
                    if link_element and link_element.get('href'):
                        link_text = link_element.get_text(strip=True)
                        feature_value = f"{link_text} - {link_element.get('href')}"
                    
                    # Clean up feature name for dictionary key
                    cleaned_feature_name = feature_name.replace(':', '').strip()
                    features_dict[cleaned_feature_name] = feature_value

        formatted_pricing_data[plan_name_key] = {
            "Base Pricing": {
                "Full Price Description": full_price_description 
            },
            "Features": features_dict
        }

    return formatted_pricing_data # Return the dictionary, not a JSON string

if __name__ == "__main__":
    asana_pricing_url = "https://asana.com/pricing"
    extracted_data = extract_asana_pricing_and_features_formatted(asana_pricing_url)
    
    if extracted_data:
        # Save the extracted data to a variable
        json_output = json.dumps(extracted_data, indent=4)
        print(json_output)
