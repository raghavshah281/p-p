import requests
from bs4 import BeautifulSoup
import json
import re

def _clean_feature_text(text):
    """Helper to clean up raw feature text from HTML."""
    # Remove checkmark symbol, redundant HTML comments, and strip whitespace
    text = text.replace('✓', '').replace('<!-- -->', '').strip()
    return text[0].upper() + text[1:] if text else ""

def extract_replit_pricing_features(html_source_code):
    """
    Extracts pricing and features information from Replit's pricing page HTML
    source code and returns it as a JSON object with a structured format.
    Prioritizes __NEXT_DATA__ JSON, then falls back to HTML scraping.
    """
    soup = BeautifulSoup(html_source_code, 'html.parser')
    plans_output = {}

    # Determine default billing cycle from HTML toggle (assuming 'yearly' is checked by default in your HTML)
    yearly_toggle_checked = soup.find('input', {'id': 'yearly', 'name': 'plan-period', 'type': 'radio', 'checked': True}) is not None

    # --- Step 1: Extract base pricing from __NEXT_DATA__ (most reliable for exact numerical values) ---
    next_data_script = soup.find('script', id='__NEXT_DATA__')
    if next_data_script:
        try:
            next_data = json.loads(next_data_script.string)
            subscription_plans = next_data.get('props', {}).get('apolloState', {}).get('ROOT_QUERY', {}).get('subscriptionPlans', {})

            plan_key_map = {
                'pro': 'Replit Core',
                'hacker': 'Hacker',
                'teams': 'Teams',
            }

            for key_in_data, display_name in plan_key_map.items():
                plan_details = subscription_plans.get(key_in_data, {})
                base_pricing = {"Monthly Price (Billed Monthly)": "Not specified", "Yearly Price (Billed Annually)": "Not specified"}

                stripe_details = plan_details.get('stripe')
                orb_details = plan_details.get('orb')

                if stripe_details:
                    monthly_cost_cents = stripe_details.get('monthlyPlanDetails', {}).get('costInUsdCents')
                    yearly_cost_cents = stripe_details.get('yearlyPlanDetails', {}).get('costInUsdCents')

                    if monthly_cost_cents is not None:
                        base_pricing["Monthly Price (Billed Monthly)"] = f"${monthly_cost_cents / 100:.2f} /month"
                    if yearly_cost_cents is not None:
                        base_pricing["Yearly Price (Billed Annually)"] = f"${yearly_cost_cents / 100:.2f} /month (billed annually)"
                elif orb_details: # Teams plan
                    monthly_cost_cents = orb_details.get('monthlyPlanDetails', {}).get('costInUsdCents')
                    yearly_cost_cents = orb_details.get('yearlyPlanDetails', {}).get('costInUsdCents')

                    if monthly_cost_cents is not None:
                        base_pricing["Monthly Price (Billed Monthly)"] = f"${monthly_cost_cents / 100:.2f} /user/month"
                    if yearly_cost_cents is not None:
                        base_pricing["Yearly Price (Billed Annually)"] = f"${yearly_cost_cents / 100:.2f} /user/month (billed annually)"
                
                plans_output[display_name] = {"Base Pricing": base_pricing, "Features": {}}
            
            # Manually add "Starter" and "Enterprise" from known data
            plans_output['Starter'] = {
                "Base Pricing": { "Monthly Price (Billed Monthly)": "Free", "Yearly Price (Billed Annually)": "Free" },
                "Features": {}
            }
            plans_output['Enterprise'] = {
                "Base Pricing": { "Monthly Price (Billed Monthly)": "Custom pricing", "Yearly Price (Billed Annually)": "Custom pricing" },
                "Features": {}
            }

        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse __NEXT_DATA__ script: {e}")
            pass # Continue to HTML scraping if JSON fails

    # --- Step 2: Populate/update pricing and features from visible HTML cards ---
    plan_cards_html = soup.find_all('div', class_=re.compile(r'css-ii9l5r|css-1ehpd5f|css-1fz70op')) 

    for card in plan_cards_html:
        plan_name_element = card.find('span', class_=re.compile(r'Text-module__.*__text'), style=re.compile(r'subhead-big'))
        if not plan_name_element:
            continue
        
        raw_plan_name = plan_name_element.get_text(strip=True)
        plan_name = raw_plan_name
        if raw_plan_name == "Core": # Standardize name
            plan_name = "Replit Core"
        
        if plan_name not in plans_output:
            plans_output[plan_name] = {"Base Pricing": {"Monthly Price (Billed Monthly)": "Not specified", "Yearly Price (Billed Annually)": "Not specified"}, "Features": {}}

        # Update pricing from visible cards (overrides __NEXT_DATA__ for active view)
        price_container = card.find('div', style=lambda s: s and 'height:50px' in s)
        if price_container:
            price_value_span = price_container.find('span', class_=re.compile(r'Text-module__.*__text'), style=re.compile(r'header-big'))
            unit_spans = price_container.find_all('span', class_=re.compile(r'css-4ta10k|Text-module__.*__multilineClamped'))
            
            displayed_price_value = price_value_span.get_text(strip=True) if price_value_span else ""
            displayed_units = " ".join([s.get_text(strip=True) for s in unit_spans]).replace('\n', ' ').strip()
            
            full_display_price = f"{displayed_price_value} {displayed_units}".strip()

            if "Free" in full_display_price:
                plans_output[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = "Free"
                plans_output[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = "Free"
            elif "Custom" in full_display_price:
                plans_output[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = "Custom pricing"
                plans_output[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = "Custom pricing"
            else:
                # If 'yearly' is checked, the displayed price is for the annual billing
                if yearly_toggle_checked:
                    # Update yearly price from HTML display
                    plans_output[plan_name]["Base Pricing"]["Yearly Price (Billed Annually)"] = full_display_price
                    # Keep monthly price from __NEXT_DATA__ if it existed, otherwise "Not specified"
                else:
                    # If 'monthly' was checked (not in this static HTML), this would be for monthly billing
                    plans_output[plan_name]["Base Pricing"]["Monthly Price (Billed Monthly)"] = full_display_price
                    # Keep yearly price from __NEXT_DATA__ if it existed, otherwise "Not specified"

        # Extract features from direct card lists
        card_features_div = card.find('div', class_=lambda x: x and 'css-oocz0h' in x)
        if card_features_div:
            for item in card_features_div.find_all('span', class_=re.compile(r'Text-module__zSV44a__text|Text-module__zSV44a__multiline')):
                feature_text = _clean_feature_text(item.get_text(strip=True))
                # Skip descriptive text that is not a specific feature or if it duplicates pricing info
                if "Everything included with" in feature_text or "credits included" in feature_text or "per user" in feature_text or "billed annually" in feature_text or "per month" in feature_text:
                    continue
                
                # Apply more specific mapping for clarity
                if "Replit Agent trial included" in feature_text:
                    plans_output[plan_name]['Features']['Agent Access'] = "Trial Included"
                elif "Full Replit Agent access" in feature_text:
                    plans_output[plan_name]['Features']['Agent Access'] = "Full Access"
                elif "$25 of monthly credits" in feature_text:
                    plans_output[plan_name]['Features']['Monthly Credits'] = "$25"
                elif "$40/mo in usage credits" in feature_text: # This captures "40/mo in usage credits included"
                    plans_output[plan_name]['Features']['Monthly Usage Credits'] = "$40"
                elif "50 Viewer seats" in feature_text:
                    plans_output[plan_name]['Features']['Viewer Seats'] = "50"
                elif "Public apps only" in feature_text:
                    plans_output[plan_name]['Features']['Public Apps'] = "Only"
                elif "10 development apps (with temporary links)" in feature_text:
                    plans_output[plan_name]['Features']['Development Apps'] = "10 (with temporary links)"
                elif "Limited build time, without long full autonomy" in feature_text:
                    plans_output[plan_name]['Features']['Build Time'] = "Limited (without long full autonomy)"
                elif "Private and public apps" in feature_text:
                    plans_output[plan_name]['Features']['App Visibility'] = "Private & Public"
                elif "Access to latest models" in feature_text:
                    plans_output[plan_name]['Features']['Latest Models Access'] = "Included"
                elif "Publish and host live apps" in feature_text:
                    plans_output[plan_name]['Features']['Publish & Host Live Apps'] = "Included"
                elif "Pay-as-you-go for additional usage" in feature_text:
                    plans_output[plan_name]['Features']['Pay-as-you-go for Additional Usage'] = "Included"
                elif "Autonomous long builds" in feature_text:
                    plans_output[plan_name]['Features']['Autonomous Long Builds'] = "Included"
                elif "Credits granted upfront on annual plan" in feature_text:
                    plans_output[plan_name]['Features']['Credits Granted Upfront (Annual)'] = "Included"
                elif "Centralized billing" in feature_text:
                    plans_output[plan_name]['Features']['Centralized Billing'] = "Included"
                elif "Role-based access control" in feature_text:
                    plans_output[plan_name]['Features']['Role-based Access Control'] = "Included"
                elif "Private deployments" in feature_text:
                    plans_output[plan_name]['Features']['Private Deployments'] = "Included"
                elif "Custom Viewer Seats" in feature_text:
                    plans_output[plan_name]['Features']['Viewer Seats'] = "Custom"
                elif "SSO/SAML" in feature_text:
                    plans_output[plan_name]['Features']['SSO/SAML'] = "Included"
                elif "SCIM" in feature_text:
                    plans_output[plan_name]['Features']['SCIM'] = "Included"
                elif "Advanced privacy controls" in feature_text:
                    plans_output[plan_name]['Features']['Advanced Privacy Controls'] = "Included"
                elif "Dedicated support" in feature_text:
                    plans_output[plan_name]['Features']['Dedicated Support'] = "Included"
                elif feature_text and feature_text not in plans_output[plan_name]['Features']:
                    plans_output[plan_name]['Features'][feature_text] = "Included"


    # --- Step 3: Extract features from the comparison table (fill in gaps or overwrite with more detail) ---
    comparison_table = soup.find('table', class_='PlanComparison-module__rGQfDa__table')
    if comparison_table:
        table_headers_raw = comparison_table.find('thead').find_all('th', class_=re.compile(r'react-aria-Column|PlanComparison-module__rGQfDa__headerHighlightColumn'))
        
        table_plan_names = []
        for th in table_headers_raw:
            span_text_element = th.find('span', class_=re.compile(r'Text-module__.*__text'))
            if span_text_element: # Check if span_text_element is not None
                span_text = span_text_element.get_text(strip=True)
                if span_text in ["Starter", "Teams", "Enterprise"]:
                    table_plan_names.append(span_text)
                elif span_text == "Core":
                    table_plan_names.append("Replit Core")
                # Ignore generic section headers like "Replit AI", "Development" etc.
            # Else, it's a non-plan header, just skip

        table_rows = comparison_table.find('tbody').find_all('tr', class_=re.compile(r'react-aria-Row|PlanComparison-module__rGQfDa__subheadRow'))
        
        for row in table_rows:
            feature_name_cell = row.find('td', class_='PlanComparison-module__rGQfDa__rowCell')
            if not feature_name_cell:
                continue

            feature_name_span = feature_name_cell.find('span', class_=re.compile(r'Text-module__.*__text'))
            if not feature_name_span:
                continue
            
            feature_key = _clean_feature_text(feature_name_span.get_text(strip=True))

            # Iterate over value cells for each plan
            value_cells = row.find_all('td', class_=re.compile(r'PlanComparison-module__rGQfDa__rowCell|PlanComparison-module__rGQfDa__rowCellHighlight'))
            
            for i, cell in enumerate(value_cells[1:]): # Skip the first cell (feature name cell)
                if i < len(table_plan_names):
                    plan_name = table_plan_names[i]
                    
                    if plan_name not in plans_output:
                        plans_output[plan_name] = {"Base Pricing": {"Monthly Price (Billed Monthly)": "Not specified", "Yearly Price (Billed Annually)": "Not specified"}, "Features": {}}

                    cell_text_raw = cell.get_text(strip=True)
                    cell_text = _clean_feature_text(cell_text_raw)
                    
                    has_checkmark = cell.find('svg', attrs={'width': '16', 'height': '16', 'fill': 'currentColor'}) is not None
                    # The UI uses absence of checkmark or specific text to imply "Not Included"
                    
                    # Prioritize more specific values from the table
                    if feature_key == "Agent" :
                         if "Limited" in cell_text.lower():
                            plans_output[plan_name]['Features']['Agent Access'] = "Limited"
                         elif has_checkmark:
                            plans_output[plan_name]['Features']['Agent Access'] = "Full Access"
                    elif feature_key == "Autonomy":
                         if "Basic" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Basic"
                         elif "Advanced" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Advanced"
                    elif feature_key == "Code Generation":
                         if "Basic" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Basic"
                         elif "Advanced" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Advanced"
                    elif feature_key == "Debugger":
                         if "Basic" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Basic"
                         elif "Advanced" in cell_text: plans_output[plan_name]['Features'][feature_key] = "Advanced"
                    elif "vCPUs" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "Memory (GiB)" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "Outbound data transfer (GiB)" in feature_key and cell_text:
                        plans_output[plan_name]['Features'][f"{feature_key} (Dev)"] = cell_text # Clarify if it's for dev environment
                    elif "Storage per app (GiB)" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "Development Time (minutes)" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "Public Apps" in feature_key and cell_text:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "Private Apps" in feature_key and has_checkmark: # Only if checkmark for Private Apps
                        plans_output[plan_name]['Features'][feature_key] = "Included"
                    elif "Collaborators" in feature_key and cell_text:
                         plans_output[plan_name]['Features'][feature_key] = cell_text
                    elif "SSH access" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = "Included" if has_checkmark else "Not Included"
                    elif "Single-tenant with VPC" in feature_key:
                         plans_output[plan_name]['Features'][feature_key] = cell_text if cell_text else "Not Included"
                    elif "Custom invoicing" in feature_key:
                         plans_output[plan_name]['Features'][feature_key] = "Included" if has_checkmark else "Not Included"
                    elif "Reserved VM deployments" in feature_key or "Autoscale deployments" in feature_key or \
                         "Autoscale compute units" in feature_key or "Autoscale requests" in feature_key or \
                         "Scheduled deployments" in feature_key or "Scheduled compute units" in feature_key or \
                         "Static deployments" in feature_key:
                         plans_output[plan_name]['Features'][feature_key] = "Included" if has_checkmark else "Not Included"
                    elif "Role-based access control" in feature_key or "SSO" in feature_key or "Member Support" in feature_key or \
                         "Member-only events" in feature_key or "Early access to new features" in feature_key or \
                         "Member community" in feature_key or "Onboarding support" in feature_key:
                        plans_output[plan_name]['Features'][feature_key] = "Included" if has_checkmark else "Not Included"
                    elif "Replit Database" in feature_key or "PostgreSQL storage (GiB)" in feature_key or "PostgreSQL compute (hours)" in feature_key or \
                         "App Storage" in feature_key or "App Storage data transfer (GiB)" in feature_key or \
                         "App Storage advanced operations" in feature_key or "App Storage basic operations" in feature_key:
                         plans_output[plan_name]['Features'][feature_key] = "Included" if has_checkmark else cell_text if cell_text else "Not Included" # Handle custom text or checkmark
                    elif has_checkmark:
                        plans_output[plan_name]['Features'][feature_key] = "Included"
                    elif cell_text:
                        plans_output[plan_name]['Features'][feature_key] = cell_text
                    else:
                        plans_output[plan_name]['Features'][feature_key] = "Not Included"


    # Final cleanup and sorting
    final_output = {}
    for plan_name in ["Starter", "Replit Core", "Teams", "Enterprise", "Hacker"]: # Ensure desired order
        if plan_name in plans_output:
            plan_data = plans_output[plan_name]
            # Remove Hacker plan if it doesn't have features listed in HTML
            if plan_name == "Hacker" and not plan_data["Features"]:
                continue
            
            # Remove empty values or duplicates from features
            cleaned_features = {}
            for k, v in plan_data['Features'].items():
                if v and v.lower() != "not included": # Only add if it's a real feature and not just "Not Included"
                    cleaned_features[k] = v
            plan_data['Features'] = cleaned_features

            final_output[plan_name] = plan_data

    return final_output


def get_replit_pricing_info(url="https://replit.com/pricing"):
    """
    Fetches the HTML from the Replit pricing URL and extracts information.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        html_source_code = response.text
        return extract_replit_pricing_features(html_source_code)
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to retrieve URL {url}: {e}"}

if __name__ == "__main__":
    replit_pricing_info = get_replit_pricing_info("https://replit.com/pricing")
    print(json.dumps(replit_pricing_info, indent=4))
