import json
import re
import requests
from bs4 import BeautifulSoup

def extract_jira_pricing_and_features(url):
    """
    Extracts pricing and features from the Atlassian Jira pricing page
    by parsing the HTML structure directly.

    Args:
        url (str): The URL of the Jira pricing page.

    Returns:
        dict: A dictionary containing the extracted pricing and features in JSON format.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to retrieve the webpage: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')

    pricing_data = {
        "plans": []
    }
    
    # Initialize detailed_features_by_plan outside any conditional block
    detailed_features_by_plan = {}

    # --- Attempt to extract pricing and highlighted features from the main plan cards ---
    # These class names are derived from the provided HTML snippet and may need adjustment
    plan_card_elements = soup.find_all('div', class_=re.compile(r'_1s1giz18|_1yxn1wk8|_1einiz18'))

    for plan_elem in plan_card_elements:
        name_tag = plan_elem.find('h4', class_='pricing-card-title') or \
                   plan_elem.find('h4', class_='_y3gn1h6o _6rthidpf _1pfhidpf')
        name = name_tag.get_text(strip=True) if name_tag else "N/A"

        one_liner_tag = plan_elem.find('p', class_='body-sm')
        one_liner = one_liner_tag.get_text(strip=True) if one_liner_tag else "N/A"

        price = "N/A"
        # Check for static price display first
        price_tag = plan_elem.find('h2', class_='pricing-card-price')
        if price_tag:
            price_text = price_tag.get_text(strip=True)
            if "Billed annually." in price_text or "Switch to Annual billing" in price_text:
                price = "Contact sales for annual billing"
            elif "$" in price_text:
                price = price_text
        
        # Fallback/enrich from window.pricingContent if available (re-attempting to find it)
        # This part could be integrated with the JSON extraction earlier if successful
        if price == "N/A" or "Contact sales" in price:
            script_tags = soup.find_all('script')
            pricing_content_json_str = None
            for script in script_tags:
                if script.string and 'window.pricingContent=Object.freeze(' in script.string:
                    match = re.search(r'window\.pricingContent=Object\.freeze\((.*?)\);', script.string, re.DOTALL)
                    if match:
                        pricing_content_json_str = match.group(1)
                        break
            
            if pricing_content_json_str:
                try:
                    full_pricing_content = json.loads(pricing_content_json_str)
                    if full_pricing_content.get("ccpPricingData") and full_pricing_content["ccpPricingData"].get("jiraSoftware"):
                        normalized_sku = plan_elem.find(attrs={"data-product-key": "jiraSoftware"}).get("href").split("edition=")[-1] if plan_elem.find(attrs={"data-product-key": "jiraSoftware"}) else ""
                        
                        if normalized_sku and normalized_sku in full_pricing_content["ccpPricingData"]["jiraSoftware"]:
                            plan_details_from_ccp = full_pricing_content["ccpPricingData"]["jiraSoftware"][normalized_sku]
                            if plan_details_from_ccp.get("defaultPricingPlans"):
                                for default_plan in plan_details_from_ccp["defaultPricingPlans"]:
                                    if "MONTHLY" in default_plan.get("primaryCycle_name", "").upper() and "per user" in one_liner.lower():
                                        if default_plan.get("items"):
                                            first_item = default_plan["items"][0]
                                            if first_item.get("tiers"):
                                                first_tier = first_item["tiers"][0]
                                                if "unitAmount" in first_tier:
                                                    unit_amount = first_tier["unitAmount"]
                                                    currency = default_plan.get("currency", "USD")
                                                    price = f"${unit_amount / 100:.2f} per user / month"
                                                break
                                    elif "ANNUAL" in default_plan.get("primaryCycle_name", "").upper() and "Billed annually" in one_liner:
                                        if default_plan.get("items"):
                                            first_item = default_plan["items"][0]
                                            if first_item.get("tiers"):
                                                first_tier = first_item["tiers"][0]
                                                if "flatAmount" in first_tier:
                                                    flat_amount = first_tier["flatAmount"]
                                                    currency = default_plan.get("currency", "USD")
                                                    price = f"${flat_amount / 100:.2f} / year"
                                                break
                except json.JSONDecodeError:
                    pass # Couldn't parse, so stick with what we have or "N/A"

        highlighted_features = []
        # Find features from <p> tags directly under the plan element
        for p_tag in plan_elem.select('div[data-testid="expand-content"] + p.body-sm, div._1yt41ejb > p.body-sm'):
            feature_text = p_tag.get_text(strip=True)
            if feature_text and not feature_text.startswith("Includes:") and not feature_text.startswith("Everything from"):
                feature_text = re.sub(r'\s*(New|Beta)\s*', '', feature_text, flags=re.IGNORECASE).strip()
                highlighted_features.append(feature_text)

        # Find features from expandable buttons
        for button in plan_elem.select('button[data-testid="expand-button"]'):
            feature_text_span = button.find('p', class_='body-sm')
            if feature_text_span:
                feature_text = feature_text_span.get_text(strip=True)
                feature_text = re.sub(r'\s*(New|Beta)\s*', '', feature_text, flags=re.IGNORECASE).strip()
                if feature_text not in highlighted_features: # Avoid duplicates
                    highlighted_features.append(feature_text)

        pricing_data["plans"].append({
            "name": name,
            "one_liner": one_liner,
            "price": price,
            "features": highlighted_features,
            "detailed_features": {} # Initialize for later population
        })

    # --- Attempt to extract detailed features from the comparison table ---
    comparison_table = soup.find('table', class_='pricing-table')
    if comparison_table:
        headers = [th.get_text(strip=True) for th in comparison_table.find('thead').find_all('th') if th.get_text(strip=True)]
        
        # Clean headers to match plan names (e.g., remove " (per user)")
        cleaned_headers = [re.sub(r'\s*\(.+\)\s*', '', h).strip() for h in headers]
        
        # Create a mapping from cleaned header name to the plan objects we've already extracted
        plan_name_to_obj = {plan["name"]: plan for plan in pricing_data["plans"]}
        
        # Initialize detailed_features for any plans not yet present in pricing_data,
        # or to ensure they all have the structure.
        for header_name in cleaned_headers[1:]: # Skip the first header which is 'Feature Name'
            if header_name not in plan_name_to_obj:
                plan_name_to_obj[header_name] = {"name": header_name, "one_liner": "N/A", "price": "N/A", "features": [], "detailed_features": {}}
                pricing_data["plans"].append(plan_name_to_obj[header_name])


        current_feature_group = None
        for row in comparison_table.find('tbody').find_all('tr'):
            # Check if this row is a feature group header
            group_header_tag = row.find('span', class_='_syaz1hlo _1bsb1osq _k48p8n31 _4t3i1wug _1e0c1ule _1i4q1hna')
            if group_header_tag:
                current_feature_group = group_header_tag.get_text(strip=True)
                continue # Move to the next row for actual features

            cells = row.find_all('td')
            if not cells:
                continue

            feature_name = cells[0].get_text(strip=True) if cells[0] else "N/A"
            # Remove expandable button icon if present in feature name
            feature_name = re.sub(r'<span>Back</span>', '', feature_name).strip()
            feature_name_parts = feature_name.split("<span>") # Remove span tags that might contain 'New' or 'Beta'
            feature_name = feature_name_parts[0].strip()
            feature_name = re.sub(r'\s*(New|Beta)\s*', '', feature_name, flags=re.IGNORECASE).strip()


            # Extract description from the expanded content if available (hidden by default)
            description_elem = cells[0].find('div', class_=re.compile(r'_clfdidpf'))
            description = description_elem.get_text(strip=True) if description_elem else ""

            # Iterate over each plan's column for this feature
            for i, plan_cell in enumerate(cells[1:]): # Skip the first cell which is feature name
                plan_header_name = cleaned_headers[i + 1] # Match to the correct plan header
                plan_status = plan_cell.get_text(strip=True)

                plan_obj = plan_name_to_obj.get(plan_header_name)
                if plan_obj:
                    if "detailed_features" not in plan_obj:
                        plan_obj["detailed_features"] = {}
                    
                    group_key = current_feature_group if current_feature_group else "General Features"
                    if group_key not in plan_obj["detailed_features"]:
                        plan_obj["detailed_features"][group_key] = []
                    
                    # Avoid adding duplicate features within the detailed_features
                    feature_exists_in_details = False
                    for existing_detail in plan_obj["detailed_features"][group_key]:
                        if existing_detail["feature"] == feature_name:
                            feature_exists_in_details = True
                            break
                            
                    if not feature_exists_in_details:
                        plan_obj["detailed_features"][group_key].append({
                            "feature": feature_name,
                            "description": description,
                            "status": plan_status # This will be like "Free", "Standard", "Checked", "100 users", etc.
                        })
    
    # Clean up plans with no actual name found
    pricing_data["plans"] = [p for p in pricing_data["plans"] if p["name"] != "N/A"]

    return pricing_data

if __name__ == "__main__":
    jira_pricing_url = "https://www.atlassian.com/software/jira/pricing"
    extracted_data = extract_jira_pricing_and_features(jira_pricing_url)
    print(json.dumps(extracted_data, indent=4))
