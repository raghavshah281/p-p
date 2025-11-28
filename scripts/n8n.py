import requests
from bs4 import BeautifulSoup
import json
import re

def extract_pricing_features_from_url(url="https://n8n.io/pricing/"):
    """
    Fetches the HTML source code from the given URL, then extracts pricing and features
    information from n8n's pricing page and returns it as a JSON object.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        html_source_code = response.text
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to retrieve URL {url}: {e}"}

    soup = BeautifulSoup(html_source_code, 'html.parser')
    plans_data = []

    # Find the main pricing section which contains individual plan cards.
    # Based on the HTML structure, elements with class 'pricing-plan' are the main cards.
    pricing_cards = soup.find_all('div', class_=lambda x: x and 'pricing-plan' in x)

    if not pricing_cards:
        return {"error": "Could not find pricing plan cards in the provided HTML."}

    for card in pricing_cards:
        plan = {}

        # 1. Plan Name
        name_element = card.find('h3', class_=lambda x: x and ('title' in x and 'title--white' in x))
        if name_element:
            plan['name'] = name_element.get_text(strip=True)
        else:
            # If no specific H3 with the title class, try a more general heading search within the card
            name_element_fallback = card.find(['h2', 'h3', 'strong'])
            if name_element_fallback:
                plan['name'] = name_element_fallback.get_text(strip=True)
            else:
                continue # Skip this card if no name can be identified

        # 2. Pricing
        # Look for the price and billing cycle.
        # The structure is often <div class="flex flex-row items-end gap-1">20€ <span ...>/mo, billed annually</span></div>
        price_main_element = card.find('div', class_=lambda x: x and 'text-headline-md' in x)
        if price_main_element:
            price_text = price_main_element.get_text(separator=" ", strip=True)
            plan['pricing'] = [price_text]
        else:
            # Handle "Contact us" or "Free" cases
            contact_us_element = card.find(text=re.compile(r'Contact sales', re.IGNORECASE)) # Changed to 'Contact sales' to match the button text
            if contact_us_element:
                plan['pricing'] = ["Contact us"]
            else:
                # Check if it's a "Free" plan if no explicit price is found
                free_trial_text = card.find(text=re.compile(r'Start free trial', re.IGNORECASE))
                if free_trial_text:
                    plan['pricing'] = ["Free trial available"]
                    # Look for other price details if it's not "Free" entirely, but has a trial
                    if "Starter" in plan.get('name', '') or "Pro" in plan.get('name', ''):
                         # Extract from the execution block itself
                        execution_value_element = card.find('p', class_=lambda x: x and 'text-xxl' in x and 'lowercase' in x)
                        if execution_value_element:
                            plan['pricing'].append(f"Starting with {execution_value_element.get_text(strip=True)} workflow executions")
                
                if not plan.get('pricing'):
                     plan['pricing'] = ["Not specified"]


        # 3. Features
        features = []
        # Features directly listed under the plan card
        features_list_elements = card.find_all('li', class_=lambda x: x and 'flex flex-row items-center' in x)
        for li in features_list_elements:
            # Extract text from the span that contains the feature description
            feature_span = li.find('span', class_='tooltip-content')
            if feature_span:
                feature_text = feature_span.get_text(strip=True)
                features.append(feature_text)
            else:
                # Fallback for features without tooltips (e.g., "Forum support" in Starter)
                direct_text = li.get_text(separator=" ", strip=True)
                # Filter out numbers/execution counts if they are not the primary feature description
                if direct_text and not re.search(r'^\d+(\.\d+)?(K|M)?\s*workflow executions', direct_text, re.IGNORECASE):
                    features.append(direct_text)
        
        plan['features'] = list(set([f for f in features if f])) # Remove duplicates and empty strings

        if plan.get('name'):
            plans_data.append(plan)

    # Process the feature comparison table for more comprehensive features
    feature_tables = soup.find_all('div', class_='feature-table-section')
    plan_names_from_table = []
    
    if feature_tables:
        # First, extract plan names from the table header to ensure consistent mapping
        # This header row is usually the first row that lists "Starter", "Pro", "Enterprise"
        header_row = feature_tables[0].find('div', class_=lambda x: x and 'flex w-full flex-nowrap items-center' in x)
        if header_row:
            # Look for spans with specific text content that are plan names
            plan_name_candidates = header_row.find_all('span', class_=lambda x: x and 'font-geomanist-book' in x)
            # Filter out the section titles from these candidates
            section_titles = ["Core features", "Developer tools", "Workflow execution", "Debugging", "Enterprise Scaling", "Security", "Collaboration", "Insights", "Support", "Billing and contract"]
            plan_names_from_table = [span.get_text(strip=True) for span in plan_name_candidates if span.get_text(strip=True) not in section_titles]
            
            # Ensure all plans found in the table header exist in plans_data
            for plan_name_in_table in plan_names_from_table:
                if not any(p['name'] == plan_name_in_table for p in plans_data):
                    plans_data.append({'name': plan_name_in_table, 'pricing': ['Not specified'], 'features': []})

        for table in feature_tables:
            feature_rows = table.find_all('div', class_=lambda x: x and 'flex w-full flex-nowrap items-center' in x)
            for row in feature_rows:
                # Extract the feature name (first column)
                feature_name_element = row.find('span', class_=lambda x: x and 'tooltip-content' in x)
                if feature_name_element:
                    feature_name = feature_name_element.get_text(strip=True)
                else:
                    # Fallback for features that don't have a tooltip
                    feature_name_div = row.find('div', class_=lambda x: x and 'text-[#666d80]' in x)
                    if feature_name_div:
                        feature_name = feature_name_div.get_text(strip=True).replace("Core features", "").replace("Developer tools", "").replace("Workflow execution", "").replace("Debugging", "").replace("Enterprise Scaling", "").replace("Security", "").replace("Collaboration", "").replace("Insights", "").replace("Support", "").replace("Billing and contract", "").strip()
                    else:
                        continue # Skip if no clear feature name can be found

                if not feature_name:
                    continue

                # Extract status/value for each plan (subsequent columns)
                status_cells = row.find_all('div', class_=lambda x: x and 'flex min-h-[56px] flex-1 items-center justify-center' in x)
                for i, cell in enumerate(status_cells):
                    if i < len(plan_names_from_table):
                        plan_name = plan_names_from_table[i]
                        
                        # Check for a checkmark SVG
                        has_checkmark = cell.find('svg', attrs={'width': '20', 'height': '20'}) is not None
                        
                        # Check for specific text indicators
                        cell_text = cell.get_text(strip=True)
                        is_self_hosted_only = "Available in self-hosted" in cell_text
                        upon_request = "Upon request" in cell_text
                        
                        # Get the plan to update
                        current_plan = next((p for p in plans_data if p['name'] == plan_name), None)
                        if current_plan:
                            if has_checkmark and feature_name not in current_plan['features']:
                                current_plan['features'].append(feature_name)
                            elif is_self_hosted_only and f"{feature_name} (Self-hosted only)" not in current_plan['features']:
                                current_plan['features'].append(f"{feature_name} (Self-hosted only)")
                            elif upon_request and f"{feature_name}: Upon request" not in current_plan['features']:
                                current_plan['features'].append(f"{feature_name}: Upon request")
                            elif cell_text and not has_checkmark and not is_self_hosted_only and not upon_request:
                                # Add the specific value if it's not a generic checkmark or "self-hosted"
                                feature_with_value = f"{feature_name}: {cell_text}"
                                if feature_with_value not in current_plan['features'] and feature_name not in current_plan['features']:
                                    current_plan['features'].append(feature_with_value)
    
    # Final cleanup and formatting
    for plan in plans_data:
        plan['pricing'] = list(set([p.replace('\n', ' ').strip() for p in plan['pricing'] if p.strip()]))
        plan['features'] = list(set([f.replace('\n', ' ').strip() for f in plan['features'] if f.strip()]))
        
        if not plan['pricing']: plan['pricing'] = ["Not specified"]
        if not plan['features']: plan['features'] = ["No specific features found"]

    return {"n8n_plans": plans_data}

if __name__ == "__main__":
    pricing_info = extract_pricing_features_from_url("https://n8n.io/pricing/")
    print(json.dumps(pricing_info, indent=4))
