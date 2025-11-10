import requests
from bs4 import BeautifulSoup
import re
import json

def extract_pricing_from_json(soup):
    """
    Extracts accurate monthly and yearly prices from the hidden JSON payload
    within the <script id="__NEXT_DATA__"> tag.
    This is much more reliable than parsing the visible HTML price elements.
    """
    try:
        # Find the script tag containing the Next.js data payload
        script_tag = soup.find('script', id='__NEXT_DATA__')
        if not script_tag:
            # Removed print statement
            return {}

        # Parse the JSON content
        data = json.loads(script_tag.string)

        # Navigate to the pricing plans within the JSON structure
        plans_data = data.get('props', {}).get('pageProps', {}).get('plans', {})

        extracted_prices = {}

        # Helper function to format prices (Original logic restored)
        def get_price(plan, interval, unit_amount_key='unit_amount'):
            plan_detail = plans_data.get(plan, {}).get('USD', {}).get(interval, {})
            amount = plan_detail.get(unit_amount_key)
            if amount is not None:
                # Convert cents (or smallest unit) to dollars
                return f"${amount / 100:.0f}"
            return "N/A"

        # Extract core plans
        for plan_name in ["plus", "business", "enterprise"]:
            monthly = get_price(plan_name, 'month')
            yearly = get_price(plan_name, 'year')

            # Note: For Notion, the yearly price displayed is the discounted rate
            # (e.g., $10/member/month billed annually), so we adjust the label.
            yearly_billed_monthly = f"{yearly}/member/month (billed yearly)"
            monthly_billed_monthly = f"{monthly}/member/month (billed monthly)"

            extracted_prices[plan_name.capitalize()] = {
                "name": plan_name.capitalize(),
                "monthly_price_raw": monthly_billed_monthly,
                "yearly_price_raw": yearly_billed_monthly,
                "features": {}
            }

        # Add Free plan manually (price is $0)
        extracted_prices["Free"] = {
            "name": "Free",
            "monthly_price_raw": "$0 / member / month",
            "yearly_price_raw": "$0 / member / month",
            "features": {}
        }

        # Handle the AI Add-on
        ai_monthly = get_price('ai', 'month')
        ai_yearly_billed_monthly = get_price('ai', 'year')

        extracted_prices["AI Add-on"] = {
            "name": "AI Add-on",
            "monthly_price_raw": f"{ai_monthly}/member/month (billed monthly)",
            "yearly_price_raw": f"{ai_yearly_billed_monthly}/member/month (billed yearly)",
            "features": {}
        }

        # Handle the Sites Custom Hostnames Add-on
        sites_monthly = get_price('sites_custom_hostnames', 'month')
        sites_yearly_billed_monthly = get_price('sites_custom_hostnames', 'year')

        extracted_prices["Custom Domains Add-on"] = {
            "name": "Custom Domains Add-on",
            "monthly_price_raw": f"{sites_monthly}/domain/month (billed monthly)",
            "yearly_price_raw": f"{sites_yearly_billed_monthly}/domain/month (billed yearly)",
            "features": {}
        }

        return extracted_prices

    except Exception as e:
        # Removed print statement
        return {}


def scrape_notion_pricing(url):
    """
    Scrapes the Notion pricing page for plans, prices, features, and limitations
    using both HTML selectors and embedded JSON data.
    """
    # Removed print statement
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text
    except requests.RequestException as e:
        # Removed print statement
        return None

    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Extract accurate, structured pricing from embedded JSON (preferred)
    pricing_data = extract_pricing_from_json(soup)

    # --- Configuration using identified selectors from provided HTML ---
    # Class for the entire feature comparison grid
    FEATURE_MATRIX_SELECTOR = '.PricingGrid_pricingGrid__eqybz'
    # Class for each feature row in the comparison grid
    FEATURE_ROW_SELECTOR = '.PricingGrid_row__bHvcz'
    # Class for the feature name column
    FEATURE_NAME_SELECTOR = '.PricingGrid_contentTextItem__pYKXw'

    # Define the column mapping for the feature matrix
    # Note: These names must match the keys used in pricing_data (Free, Plus, Business, Enterprise)
    plan_columns_map = {
        1: "Free",
        2: "Plus",
        3: "Business",
        4: "Enterprise"
    }

    # --- 2. Extract Detailed Features Matrix from HTML ---
    # Removed print statement
    feature_matrix = soup.select_one(FEATURE_MATRIX_SELECTOR)

    if feature_matrix:
        feature_rows = feature_matrix.select(FEATURE_ROW_SELECTOR)

        for row in feature_rows:
            feature_name = "Unknown Feature"
            try:
                # First child div contains the feature name
                feature_name_element = row.select_one(FEATURE_NAME_SELECTOR)
                feature_name = feature_name_element.get_text(strip=True) if feature_name_element else "Unknown Feature"

                # We need to skip rows that are just section headers (like "Content", "Notion AI", etc.)
                if not feature_name or row.select_one('.PricingGrid_sectionLabel___YnU3'):
                     continue

                # The columns (plan values) start from the second child div
                plan_columns = row.find_all('div', recursive=False)[1:]

                for i, column in enumerate(plan_columns):
                    plan_index = i + 1
                    plan_name = plan_columns_map.get(plan_index)

                    if not plan_name or plan_name not in pricing_data:
                        continue

                    # Extract the value/status for this feature
                    # Check for an embedded SVG (which usually indicates a checkmark/inclusion)
                    if column.select_one('svg'):
                        status = "Included"
                        # Fallback to text if the SVG is for something else (e.g., custom domains fee text)
                        if column.get_text(strip=True) and column.get_text(strip=True) not in [""]:
                             status = column.get_text(strip=True)
                    else:
                        # Otherwise, extract the text (e.g., '7 days', 'Unlimited', 'Basic')
                        status = column.get_text(strip=True) or "Not Included"

                    # Clean up the feature name to include nested details (like Beta tags)
                    full_feature_name = feature_name
                    beta_badge = row.select_one('.PricingGrid_betaBadge__zJ7lH')
                    if beta_badge:
                        full_feature_name += f" ({beta_badge.get_text(strip=True)})"

                    # Add feature to the correct plan
                    pricing_data[plan_name]["features"][full_feature_name] = status

            except Exception as e:
                # Removed print statement
                continue
    else:
        # Removed print statement
        pass


    # Reformat the final output data
    final_output = {}
    for key, data in pricing_data.items():
        if key in ["AI Add-on", "Custom Domains Add-on"]:
            # Keep add-ons separate from core plans for cleaner presentation
            continue

        # Combine base pricing and features
        plan_name = data['name']
        final_output[plan_name] = {
            "Base Pricing": {
                "Monthly Price (Billed Monthly)": data.get("monthly_price_raw", "N/A"),
                "Yearly Price (Billed Annually)": data.get("yearly_price_raw", "N/A"),
            },
            "Features": data['features']
        }

    # Add add-ons as a special section if they were extracted
    if "AI Add-on" in pricing_data or "Custom Domains Add-on" in pricing_data:
        final_output["Add-ons"] = {}
        if "AI Add-on" in pricing_data:
             ai_data = pricing_data["AI Add-on"]
             final_output["Add-ons"][ai_data["name"]] = {
                "Monthly Price (Billed Monthly)": ai_data.get("monthly_price_raw", "N/A"),
                "Yearly Price (Billed Annually)": ai_data.get("yearly_price_raw", "N/A"),
             }
        if "Custom Domains Add-on" in pricing_data:
             sites_data = pricing_data["Custom Domains Add-on"]
             final_output["Add-ons"][sites_data["name"]] = {
                "Monthly Price (Billed Monthly)": sites_data.get("monthly_price_raw", "N/A"),
                "Yearly Price (Billed Annually)": sites_data.get("yearly_price_raw", "N/A"),
             }


    return final_output

# --- Main Execution (Modified to output ONLY JSON) ---
if __name__ == "__main__":
    # The URL requested by the user
    target_url = "https://www.notion.com/pricing"

    # Run the scraper
    scraped_data = scrape_notion_pricing(target_url)

    if scraped_data:
        # Output the results in a clean JSON format
        output_json = json.dumps(scraped_data, indent=4)
        print(output_json)
