import requests
from bs4 import BeautifulSoup
import json
import re

def extract_airtable_pricing_from_source(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Could not retrieve the webpage: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')

    script_tags = soup.find_all('script', nonce=True)

    init_data_script_content = None
    for script in script_tags:
        script_content = script.get_text()
        if 'window.initData = {' in script_content:
            init_data_script_content = script_content
            break

    if not init_data_script_content:
        return {"error": "Could not find 'window.initData' in any script tag. The HTML structure might have changed."}

    start_index = init_data_script_content.find('window.initData = {')
    if start_index == -1:
        return {"error": "Could not locate 'window.initData = {' in the script content."}
    
    start_index += len('window.initData = ')

    brace_count = 0
    json_str_builder = []
    end_index = -1

    for i in range(start_index, len(init_data_script_content)):
        char = init_data_script_content[i]
        json_str_builder.append(char)

        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1

        if brace_count == 0:
            end_index = i
            break
            
    if end_index == -1:
        return {"error": "Could not find matching closing brace for the 'window.initData' object."}

    json_str = "".join(json_str_builder).strip()

    # Attempt to fix trailing commas, which are common in JS object literals but invalid in JSON
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    # Attempt to quote unquoted keys
    json_str = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_str)

    try:
        init_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        start_error_idx = max(0, e.pos - 50)
        end_error_idx = min(len(json_str), e.pos + 50)
        error_context = json_str[start_error_idx:end_error_idx]
        return {"error": f"Failed to decode JSON from initData: {e}. Problematic snippet around char {e.pos}: '{error_context}'"}

    # --- Restructuring to desired output format ---
    restructured_pricing = {}

    # Helper to map Airtable plan data to the desired Notion-like structure
    def map_airtable_plan_to_notion_structure(plan_data, billing_cycle):
        plan_name = plan_data.get('name', 'N/A')
        # Standardize plan names for output keys (e.g., "Team Monthly" -> "Team", "2023 Free" -> "Free")
        # You might need to adjust these mappings based on exact desired plan names.
        if "Monthly Self-serve Business" in plan_name:
            output_plan_key = "Business" # Renaming to align with common tiers
        elif "Annual Self-serve Business" in plan_name:
            output_plan_key = "Business"
        elif "Team" in plan_name:
            output_plan_key = "Team" # Changed from "Pro" to "Team" for consistency with Airtable's naming
        elif "Free" in plan_name:
            output_plan_key = "Free"
        elif "Enterprise Scale" in plan_name:
            output_plan_key = "Enterprise"
        elif "Pro Starter Pack" in plan_name:
            output_plan_key = "Starter" # New category for this specific pack
        else:
            output_plan_key = plan_name # Fallback

        if output_plan_key not in restructured_pricing:
            restructured_pricing[output_plan_key] = {
                "Base Pricing": {
                    "Monthly Price (Billed Monthly)": "Not Available",
                    "Yearly Price (Billed Annually)": "Not Available"
                },
                "Features": {}
            }

        price_per_month_dollars = plan_data.get('costPerUserPerMonthInCents', 0) / 100
        price_string = f"${price_per_month_dollars:.0f}/member/month (billed {billing_cycle})" if price_per_month_dollars > 0 else "$0 / member / month"
        if plan_data.get('fixedCostPerCommitmentInCents', 0) > 0:
             fixed_cost_dollars = plan_data.get('fixedCostPerCommitmentInCents', 0) / 100
             price_string = f"${fixed_cost_dollars:.0f} (for {plan_data.get('numCollaboratorsIncludedInFixedCost', 0)} members) + ${price_per_month_dollars:.0f}/member/month (billed {billing_cycle})"


        if billing_cycle == 'monthly':
            restructured_pricing[output_plan_key]["Base Pricing"]["Monthly Price (Billed Monthly)"] = price_string
        else: # annual
            restructured_pricing[output_plan_key]["Base Pricing"]["Yearly Price (Billed Annually)"] = price_string

        # Map Airtable features to Notion-like feature names (adjust as needed)
        features = restructured_pricing[output_plan_key]["Features"]
        
        # Direct Mappings
        features["Records per Base"] = plan_data.get('maxRowsPerApplication', 'N/A')
        features["Attachment space per Base"] = f"{plan_data.get('maxTotalAttachmentSizeInBytes', 0) / (1024**3):.0f}GB" if plan_data.get('maxTotalAttachmentSizeInBytes', 0) > 0 else "0GB"
        features["Revision & Snapshot History"] = f"{plan_data.get('maxRevisionHistoryDays', 0)} days" if plan_data.get('maxRevisionHistoryDays', 0) > 0 else "N/A"
        features["Automation runs per month"] = f"{plan_data.get('maxNumWorkflowExecutionsPerMonth', 0):,}" if plan_data.get('maxNumWorkflowExecutionsPerMonth', 0) is not None else "N/A"
        features["AI Credits per user per month"] = plan_data.get('aiCreditsPerUserPerMonth', 0)
        features["Synced tables per application"] = plan_data.get('maxSyncedTablesPerApplication', 'N/A')
        features["Non-collaborators emailed by automations per day"] = plan_data.get('maxNonCollaboratorsEmailedByAutomationsPerDay', 'N/A')
        features["Unlimited Bases"] = "Included" if '- Unlimited bases' in plan_data.get('descriptionMarkdown', '') else "Not Included"

        # Features from description markdown
        description = plan_data.get('descriptionMarkdown', '')
        features["Public forms"] = "Included" if "Public forms" in description else "Not Included"
        features["Priority support"] = "Included" if "Priority support" in description else "Not Included"
        features["Dedicated customer success manager"] = "Included" if "Dedicated customer success manager" in description else "Not Included"
        features["SAML/SSO"] = "Included" if "SAML/SSO" in description else "Not Included"
        
        # Additional features if present in markdown and relevant
        if "automatic syncing" in description:
            features["Automatic Syncing"] = "Included"

        # Fill in 'Not Included' for features not explicitly mentioned if you want them always present
        # Example:
        # features["Enterprise search"] = features.get("Enterprise search", "Not Included")
        # This requires knowing all possible features beforehand. For now, only explicitly mentioned ones are added.

        # Remove redundant 'other_description_markdown' if you've extracted all details from it
        # features['raw_description_markdown'] = description.replace('\n', ', ').strip() # Optional: keep raw markdown

    if 'monthlyPlansToDisplay' in init_data:
        for plan in init_data['monthlyPlansToDisplay']:
            map_airtable_plan_to_notion_structure(plan, 'monthly')
    
    if 'annualPlansToDisplay' in init_data:
        for plan in init_data['annualPlansToDisplay']:
            map_airtable_plan_to_notion_structure(plan, 'annual')

    # Handle the "Free" plan's specific price display
    if "Free" in restructured_pricing:
        restructured_pricing["Free"]["Base Pricing"]["Monthly Price (Billed Monthly)"] = "$0 / member / month"
        restructured_pricing["Free"]["Base Pricing"]["Yearly Price (Billed Annually)"] = "$0 / member / month"

    # Since Airtable doesn't have "Add-ons" in window.initData in the same way,
    # you might need to manually define or scrape these if they exist elsewhere.
    # For now, I'll add a placeholder if you want it to appear.
    # if "Add-ons" not in restructured_pricing:
    #     restructured_pricing["Add-ons"] = {
    #         "AI Add-on": {
    #             "Monthly Price (Billed Monthly)": "N/A",
    #             "Yearly Price (Billed Annually)": "N/A"
    #         },
    #         "Custom Domains Add-on": {
    #             "Monthly Price (Billed Monthly)": "N/A",
    #             "Yearly Price (Billed Annually)": "N/A"
    #         }
    #     }
    # For Airtable, "AI Credits" are included per user per month in the main plan, not as a separate add-on in this data.

    return restructured_pricing

# URL of the Airtable pricing page
url = "https://airtable.com/pricing"
pricing_data = extract_airtable_pricing_from_source(url)

json_output = json.dumps(pricing_data, indent=4)
print(json_output)
