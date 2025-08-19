import os
from pyairtable import Api
import json
from openai import OpenAI
from datetime import datetime
from app.exchange_rates import get_exchange_rates
import time

api = Api(os.getenv("AIRTABLE_API_KEY"))
base = api.base(os.getenv("AIRTABLE_BASE_ID"))
applicant_table = base.table(os.getenv("AIRTABLE_APPLICANTS_ID"))
work_table = base.table(os.getenv("AIRTABLE_WORK_ID"))
salary_table = base.table(os.getenv("AIRTABLE_SALARY_ID"))
shortlist_table = base.table(os.getenv("AIRTABLE_SHORTLIST_ID"))
details_table = base.table(os.getenv("AIRTABLE_DETAILS_ID"))
applicant_data_table = []

def main():
    # Grab all the Applicant IDs from the applicants table
    applicants = applicant_table.all()
    # For each applicant, get their associated data from Personal Details, Work Experience, and Salary Preferences
    for applicant in applicants:
        old_applicant_json = applicant["fields"].get("Compressed JSON", [])
        old_applicant_data = json.loads(old_applicant_json)
        applicant_id = applicant["fields"]["Applicant ID"]
        personal_details = details_table.all(formula='IF({Applicant}="' + applicant_id + '",TRUE(),FALSE())')
        work_experience = work_table.all(formula='IF({Applicant}="' + applicant_id + '",TRUE(),FALSE())')
        salary_preferences = salary_table.all(formula='IF({Applicant}="' + applicant_id + '",TRUE(),FALSE())')
        all_work_experience = []
        complete = True

        # Clean up the data so it looks better in the JSON
        for work in work_experience:
            work_experience_data = {
                "Company": work["fields"]["Company"],
                "Title": work["fields"]["Title"],
                "Start Date": work["fields"]["Start"],
                "End Date": work["fields"]["End"],
                "Technologies": work["fields"]["Technologies"]
            }
            all_work_experience.append(work_experience_data)
        
        if len(work_experience) == 0:
            complete = False

        if len(salary_preferences) > 0:
            salary_preferences[0]["fields"].pop("Salary Preference ID")
            salary_preferences[0]["fields"].pop("Applicant")
        else:
            complete = False
        if len(personal_details) > 0:
            personal_details[0]["fields"].pop("Applicant ID")
        else:
            complete = False
        
        applicant_data = {
            "Personal Details": personal_details[0]["fields"],
            "Work Experience": all_work_experience,
            "Salary Preferences": salary_preferences[0]["fields"]
        }
        # Populate Compressed_Json field with the JSON object
        try:
            applicant_table.update(applicant["id"], {"Applicant ID": applicant_id, "Compressed JSON": json.dumps(applicant_data)})
            applicant_data_table.append({"id": applicant["id"], "data": applicant_data})
            print(f"Updated JSON for {applicant_id}")
        except Exception as e:
            print(f"Error updating applicant {applicant_id}: {e}")

        if complete:
            # Evaluate the applicant and add to shortlist if they meet the criteria
            passed, explanation = evaluate_applicant(applicant_data)
            if passed:
                shortlist = shortlist_table.all(formula='IF({Applicant}="' + applicant_id + '",TRUE(),FALSE())')
                if len(shortlist) == 0:
                    shortlist_table.create(fields={
                        "Applicant": [applicant["id"]],
                        "Score Reason": explanation,
                        "Compressed JSON": json.dumps(applicant_data)
                        }
                    )
                    applicant_table.update(applicant["id"], {"Shortlist Status": "Shortlisted"})
                    print(f"Added {applicant_id} to shortlist")
                else:
                    shortlist_table.update(shortlist[0]["id"], {
                        "Applicant": [applicant["id"]],
                        "Score Reason": explanation, 
                        "Compressed JSON": json.dumps(applicant_data)
                        }
                    )
                    print(f"Updated {applicant_id} in shortlist")
            # If the applicant data has changed, run the LLM eval
            if applicant_data != old_applicant_data:
                print(f"Running LLM eval for {applicant_id}")
                Summary, Score, _, FollowUps = LLM_eval(applicant_data)
                print(f"LLM eval complete for {applicant_id}")
                # Convert FollowUps to a nicely formatted list of bullets
                FollowUps = "\n".join([f"- {followUp}" for followUp in FollowUps])
                applicant_table.update(applicant["id"], {"Applicant ID": applicant_id, "Compressed JSON": json.dumps(applicant_data),"LLM Summary": Summary, "LLM Score": Score, "LLM Follow-Ups": FollowUps})

def currency_lookup(currency_code):
    return get_exchange_rates(currency_code.upper(), target_currencies=["USD"])["USD"]

## Handle shortlist evaluation
## Curent shortlist rules:
## - Has a Preferred Rate less than 100 USD/hr
## - Has availability of at least 20 hours per week
## - Has a Location in the US, Canada, Germany, UK, or India
## - Has at least 4 years of experience OR has worked at a Tier 1 company (Google, Meta, OpenAI, etc.)

def evaluate_applicant(applicant_data):
    #Given the applicant data and shortlist criteria, determine if the applicant meets the criteria
    ACCEPTABLE_COMPANIES = ["Google", "Meta", "OpenAI", "Apple", "Amazon", "Microsoft", "Tesla", "SpaceX", "Alphabet", "Alibaba", "Tencent", "Samsung", "Sony", "Nintendo", "EA"]
    ACCEPTABLE_LOCATIONS = ["US", "Canada", "Germany", "UK", "India"]
    EXPLANATION = ""
    passed = False
    time_working = 0
    tier_1_companies = []
    
    # Normalize the requested rate to USD
    if applicant_data["Salary Preferences"]["Currency"] == "USD":
        normalized_rate = applicant_data["Salary Preferences"]["Preferred Rate"]
    else:
        conversion = currency_lookup(applicant_data["Salary Preferences"]["Currency"])
        normalized_rate = applicant_data["Salary Preferences"]["Preferred Rate"] * conversion
        normalized_rate = round(normalized_rate, 2) # Round to 2 decimal places
    applicant_location = applicant_data["Personal Details"]["Location"]

    # Normalize the location if it's in the list of acceptable locations (i.e. "New York, USA" -> "US")
    for location in ACCEPTABLE_LOCATIONS:
        if location.lower() in applicant_location.lower():
            applicant_location = location
            break

    availability = applicant_data["Salary Preferences"]["Availability (hrs/week)"]

    # Calculate the time working and if the applicant has worked at a Tier 1 company
    for work in applicant_data["Work Experience"]:
        if work["Company"] in ACCEPTABLE_COMPANIES:
            tier_1_companies.append(work["Company"])
        start_str = work.get("Start Date")
        end_str = work.get("End Date")
        if not start_str:
            continue
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
        except Exception:
            continue
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d")
        except Exception:
            end_date = datetime.now()
        # Calculate duration in years
        duration_years = (end_date - start_date).days / 365.25
        time_working += duration_years
    time_working = round(time_working, 1)

    if len(tier_1_companies) > 0 or time_working >= 4:
        if normalized_rate < 100 and availability >= 20 and applicant_location in ACCEPTABLE_LOCATIONS:
            passed = True
            EXPLANATION = f"""
            The applicant meets the criteria due to the following:
            Total time working: {time_working} years
            Tier 1 companies worked at: {str(tier_1_companies)[1:-1].replace("'", "")}
            Preferred Rate (USD): {normalized_rate}
            Location: {applicant_location}
            Availability (hrs/week): {availability}
            """
        else:
            EXPLANATION = f"""
            The applicant does not meet the criteria. Relevant information:
            Total time working: {time_working}
            Tier 1 companies worked at: {str(tier_1_companies)[1:-1]}
            Preferred Rate (USD): {normalized_rate}
            Location: {applicant_location}
            Availability (hrs/week): {availability}
            """
    return (passed, EXPLANATION)

def LLM_eval(applicant_data):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    failure_count = 0
    while failure_count < 3:
        try:
            response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": """You are a recruiting analyst. Given this JSON applicant profile, do four things:
                    1. Provide a concise 75-word summary.
                    2. Rate overall candidate quality from 1-10 (higher is better).
                    3. List any data gaps or inconsistencies you notice.
                    4. Suggest up to three follow-up questions to clarify gaps.

                    Return in JSON format exactly the fields below. ONLY return the JSON object, no other text:
                    "Summary": <text>
                    "Score": <integer>
                    "Issues": <comma-separated list or 'None'>
                    "Follow-Ups": <bullet list>:
                """},
                {"role": "user", "content": "Evaluate the following applicant: " + json.dumps(applicant_data)}
            ],
            max_completion_tokens=10000,
            timeout=15
        )
            response_json = json.loads(response.choices[0].message.content)
            return response_json["Summary"], response_json["Score"], response_json["Issues"], response_json["Follow-Ups"]
        except Exception as e:
            print(f"Error evaluating applicant {applicant_data['id']}: {e}")
            failure_count += 1
            backoff_time = 2 ** failure_count
            time.sleep(backoff_time)
    return None, None, None, None

if __name__ == "__main__":
    main()