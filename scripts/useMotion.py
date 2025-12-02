import requests
from bs4 import BeautifulSoup
import json

def extract_motion_pricing_detailed(url):
    try:
        # 1. Fetch the HTML content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # 2. Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 3. Locate the SSR data script tag
        script_tag = soup.find('script', id='__ssr_data__')

        if not script_tag:
            return json.dumps({"error": "Could not find SSR data script tag"}, indent=4)

        # 4. Load the raw JSON data
        raw_data = json.loads(script_tag.string)
        tiers = raw_data.get('tiers', [])

        # 5. Build a "Master List" of features to normalize the output
        all_possible_features = set()
        for tier in tiers:
            for bullet in tier.get('bullets', []):
                # We skip specific credit amount bullets to handle them as a standardized key later
                if "credits/seat/month" not in bullet:
                    all_possible_features.add(bullet)
        
        sorted_master_features = sorted(list(all_possible_features))

        # 6. Helper function to format price strings
        def format_price(amount, unit_label="member", frequency="monthly"):
            if isinstance(amount, (int, float)) and amount > 0:
                # e.g., "$19/member/month (billed annually)"
                return f"${amount}/{unit_label}/month (billed {frequency})"
            elif amount == -1 or amount == "Custom Pricing":
                return "Custom Pricing"
            return str(amount)

        # 7. Construct the Final Output Dictionary
        final_output = {}

        for tier in tiers:
            base_title = tier.get("title")
            pricing_raw = tier.get("pricing", {})
            features_raw = tier.get("bullets", [])
            credits_val = tier.get("includedCredits")

            # --- Prepare Feature Map ---
            # This map is consistent for both Individual and Team variants of the same plan
            features_map = {}
            
            # Handle Credits
            if credits_val == -1:
                features_map["AI Credits"] = "Custom"
            else:
                features_map["AI Credits"] = f"{credits_val:,} credits/month"

            # Handle Bullets (Included vs Not Included)
            plan_bullets_set = set(features_raw)
            for feature in sorted_master_features:
                if feature in plan_bullets_set:
                    features_map[feature] = "Included"
                else:
                    features_map[feature] = "Not Included"

            # --- Logic: Handle Enterprise vs Standard Plans ---
            # Enterprise usually doesn't distinguish Individual vs Team in the same way, 
            # but standard plans (Pro AI, Business AI) strictly have both pricing models.

            is_enterprise = base_title.lower() == "enterprise"

            if is_enterprise:
                # Add just one entry for Enterprise
                final_output[base_title] = {
                    "Base Pricing": {
                        "Monthly Price (Billed Monthly)": "Custom Pricing",
                        "Yearly Price (Billed Annually)": "Custom Pricing"
                    },
                    "Features": features_map
                }
            else:
                # --- Create INDIVIDUAL Variant ---
                ind_monthly = pricing_raw.get("individualMonthly", {}).get("total", "N/A")
                ind_annually = pricing_raw.get("individualAnnually", {}).get("total", "N/A")

                final_output[f"{base_title} (Individual)"] = {
                    "Base Pricing": {
                        "Monthly Price (Billed Monthly)": format_price(ind_monthly, "user", "monthly"),
                        "Yearly Price (Billed Annually)": format_price(ind_annually, "user", "annually")
                    },
                    "Features": features_map
                }

                # --- Create TEAM Variant ---
                # "perSeat" is usually the metric for teams
                team_monthly = pricing_raw.get("monthly", {}).get("perSeat", "N/A")
                team_annually = pricing_raw.get("annually", {}).get("perSeat", "N/A")

                final_output[f"{base_title} (Team)"] = {
                    "Base Pricing": {
                        "Monthly Price (Billed Monthly)": format_price(team_monthly, "member", "monthly"),
                        "Yearly Price (Billed Annually)": format_price(team_annually, "member", "annually")
                    },
                    "Features": features_map
                }

        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=4)

if __name__ == "__main__":
    target_url = "https://www.usemotion.com/pricing"
    print(extract_motion_pricing_detailed(target_url))
