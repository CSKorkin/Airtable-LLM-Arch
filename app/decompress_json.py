import os
from pyairtable import Api
import json

api = Api(os.getenv("AIRTABLE_API_KEY"))
base = api.base(os.getenv("AIRTABLE_BASE_ID"))
applicant_table = base.table(os.getenv("AIRTABLE_APPLICANTS_ID"))
work_table = base.table(os.getenv("AIRTABLE_WORK_ID"))
salary_table = base.table(os.getenv("AIRTABLE_SALARY_ID"))
shortlist_table = base.table(os.getenv("AIRTABLE_SHORTLIST_ID"))
details_table = base.table(os.getenv("AIRTABLE_DETAILS_ID"))

def main():
    # Clear out the subtables to prevent duplicates
    details_records = [record["id"] for record in details_table.all()]
    work_records = [record["id"] for record in work_table.all()]
    salary_records = [record["id"] for record in salary_table.all()]
    details_table.batch_delete(details_records)
    work_table.batch_delete(work_records)
    salary_table.batch_delete(salary_records)

    # Grab all the Applicant IDs from the applicants table
    applicants = applicant_table.all(fields=["Applicant ID", "Compressed JSON"])
    # For each applicant, get their associated data from Personal Details, Work Experience, and Salary Preferences
    for applicant in applicants:
        applicant_id = applicant["fields"]["Applicant ID"]
        applicant_data = applicant["fields"]["Compressed JSON"]
        applicant_data = json.loads(applicant_data)
        personal_details = applicant_data["Personal Details"]
        work_experience = applicant_data["Work Experience"]
        salary_preferences = applicant_data["Salary Preferences"]

        # Populate the Personal Details table
        if len(personal_details) > 0:
            new_details = {"Applicant": [applicant["id"]], "Full Name": personal_details["Full Name"], "Email": personal_details["Email"], "LinkedIn": personal_details["LinkedIn"], "Location": personal_details["Location"]}
        details_table.create(new_details)
        # Populate the Work Experience table
        for work in work_experience:
            new_work = {"Applicant": [applicant["id"]], "Company": work["Company"], "Title": work["Title"], "Start": work["Start Date"], "End": work["End Date"], "Technologies": work["Technologies"]}
            work_table.create(new_work)
        # Populate the Salary Preferences table
        if len(salary_preferences) > 0:
            new_salary = {"Applicant": [applicant["id"]], "Preferred Rate": salary_preferences["Preferred Rate"], "Currency": salary_preferences["Currency"], "Minimum Rate": salary_preferences["Minimum Rate"], "Availability (hrs/week)": salary_preferences["Availability (hrs/week)"]}
            salary_table.create(new_salary)

if __name__ == "__main__":
    main()