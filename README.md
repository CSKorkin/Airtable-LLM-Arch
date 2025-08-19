## Airtable Candidate JSON Pipeline

### Overview

This repository contains a lightweight Python pipeline for managing candidate data stored in Airtable:

- **create_json.py**: Reads normalized candidate data across multiple Airtable tables, builds a single "Compressed JSON" blob per applicant, runs rules-based shortlisting, and optionally triggers an LLM evaluation. Results are written back to Airtable.
- **decompress_json.py**: Clears and rehydrates normalized Airtable tables from each applicant's "Compressed JSON" field.
- **exchange_rates.py**: Utility that fetches and caches fiat exchange rates from the European Central Bank to normalize compensation across currencies.

Use this pipeline to keep a denormalized snapshot of each applicant, auto-shortlist based on criteria, and enrich profiles with an LLM-generated summary, score, and follow-ups.

### Repository layout

- `create_json.py`: Main ingestion, compression, shortlist evaluation, and LLM enrichment.
- `decompress_json.py`: Rebuilds normalized tables from `Compressed JSON`.
- `exchange_rates.py`: ECB-backed exchange rates with on-disk caching.
- `example.json`: Example of the compressed applicant JSON shape.

### Prerequisites

- Python 3.10+
- Airtable base with the tables/fields listed below
- API keys:
  - Airtable API key and Base/Table IDs
  - OpenAI API key (for LLM evaluation)

### Dependencies
- pyairtable 
- openai 
- requests
```


### Configuration

Set the following environment variables:

```bash
export AIRTABLE_API_KEY=your_airtable_api_key
export AIRTABLE_BASE_ID=appxxxxxxxxxxxxxx

# Table IDs (or table names if your pyairtable usage resolves them). These are the IDs used in this project:
export AIRTABLE_APPLICANTS_ID=tblApplicantsXXXXXXXX
export AIRTABLE_WORK_ID=tblWorkXXXXXXXX
export AIRTABLE_SALARY_ID=tblSalaryXXXXXXXX
export AIRTABLE_SHORTLIST_ID=tblShortlistXXXXXXXX
export AIRTABLE_DETAILS_ID=tblDetailsXXXXXXXX

export OPENAI_API_KEY=your_openai_api_key
```

If you prefer a `.env` file, add the above lines there and ensure your shell loads it before running the scripts.

### Airtable base schema

The scripts assume the following tables and fields (names are case-sensitive):

- `Applicants`
  - **Applicant ID** (text) — unique per applicant
  - **Compressed JSON** (long text)
  - **LLM Summary** (long text)
  - **LLM Score** (number)
  - **LLM Follow-Ups** (long text)

- `Personal Details` (referenced as `details_table`)
  - **Applicant** (linked to `Applicants`)
  - **Full Name** (text)
  - **Email** (email)
  - **LinkedIn** (url)
  - **Location** (text)

- `Work Experience` (referenced as `work_table`)
  - **Applicant** (linked to `Applicants`)
  - **Company** (text)
  - **Title** (text)
  - **Start** (date)
  - **End** (date)
  - **Technologies** (text)

- `Salary Preferences` (referenced as `salary_table`)
  - **Applicant** (linked to `Applicants`)
  - **Preferred Rate** (number - preferred hourly rate)
  - **Minimum Rate** (number - preferred hourly rate)
  - **Currency** (single select; ISO code like USD, EUR, INR, etc.)
  - **Availability (hrs/week)** (number)

- `Shortlist` (referenced in code as `shortlist_table`)
  - **Applicant** (linked to `Applicants`)
  - **Score Reason** (long text)
  - **Compressed JSON** (long text)

Note: `decompress_json.py` is a destructive operation against the tables (`Personal Details`, `Work Experience`, `Salary Preferences`) and assumes they can be safely cleared and repopulated. It calls `batch_delete` on those tables at startup. Data stored in the Compressed JSON field is considered the source of truth - if information is added and `decompress_json.py` is run before `create_json.py` all uncompressed data will be lost.

### Usage

- **Generate compressed JSON, evaluate, and write back to Airtable**

  ```bash
  python create_json.py
  ```

  What it does:
  - Reads each record in `Applicants` with fields `Applicant ID`, `Compressed JSON`.
  - Queries related `Personal Details`, `Work Experience`, and `Salary Preferences` by `Applicant`.
  - Builds a consolidated JSON structure per applicant and writes it to `Compressed JSON`.
  - Evaluates shortlist eligibility using rules (see below). Writes/updates a `Shortlist` record with `Score Reason` and `Compressed JSON` when criteria are met.
  - Runs an LLM evaluation and updates `LLM Summary`, `LLM Score`, `LLM Follow-Ups` on `Applicants`.

- **Decompress (rehydrate) normalized tables from `Compressed JSON`**

  ```bash
  python decompress_json.py
  ```

  What it does:
  - Clears `Personal Details`, `Work Experience`, and `Salary Preferences` tables.
  - Iterates `Applicants`, parses `Compressed JSON`, and recreates normalized records, linking them back to each applicant.

### How it works

- **Data collection and normalization** (`create_json.py`)
  - Fetches related rows per applicant and constructs a JSON shape:
    - `Personal Details` (single-object)
    - `Work Experience` (list of jobs)
    - `Salary Preferences` (single-object)
  - Writes the resulting JSON to `Applicants.Compressed JSON`.

- **Shortlist rules** (`create_json.py` → `evaluate_applicant`)
  - Normalizes `Preferred Rate` to USD using the ECB conversion utility.
  - Accepts candidates who meet all of:
    - Rate < 100 USD/hr
    - Availability ≥ 20 hours/week
    - Location in one of: US, Canada, Germany, UK, India (case-insensitive match within location string)
    - And either: at least 4 years cumulative experience, or experience at a Tier 1 company (e.g., Google, Meta, OpenAI, etc.)
  - If you wish to modify these rules, you can do one of the following:
    - Update the ACCEPTED_COMPANIES or ACCEPTED_LOCATIONS array to add/remove valid Tier 1 companies and locations while keeping the overall logic the same.
	- Update evaluate_applicant() to add new rules and logic. When doing so, ensure the return remains as (passed, explanation), with passed as a bool and 
	  explanation as a human-readable string.

- **Currency normalization** (`exchange_rates.py`)
  - Downloads daily rates from the [ECB eurofxref history](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip).
  - Caches the dataset for 24 hours in a temp directory to avoid repeat downloads.
  - Converts from any supported currency to the desired base (USD in this project).

- **LLM evaluation** (`create_json.py` → `LLM_eval`)
  - Sends the consolidated applicant JSON to OpenAI Chat Completions (model `gpt-5`).
  - Expects a JSON object with fields: `Summary`, `Score`, `Issues`, `Follow-Ups`.
  - Writes these back to the `Applicants` table.
  - Implements a max return token threshold of 10,000 tokens. If the model errors, it will retry up to 3 times with increasing backoff 

### Example compressed JSON

```json
{
  "Personal Details": {
    "Full Name": "Alex Johnson",
    "Email": "alex.johnson@example.com",
    "LinkedIn": "linkedin.com/in/alexjohnson",
    "Location": "New York, USA"
  },
  "Work Experience": [
    {
      "Company": "TechNova",
      "Title": "Software Engineer",
      "Start Date": "2019-06-01",
      "End Date": "2022-08-01",
      "Technologies": "Python, React, AWS"
    },
    {
      "Company": "Google",
      "Title": "Backend Developer",
      "Start Date": "2017-01-01",
      "End Date": "2019-05-01",
      "Technologies": "Node.js, PostgreSQL, Docker"
    }
  ],
  "Salary Preferences": {
    "Preferred Rate": 120000,
    "Minimum Rate": 100000,
    "Currency": "USD",
    "Availability (hrs/week)": 40
  }
}
```

### Operational notes

- **Environment loading**: Ensure all required env vars are present in your shell before running the scripts.
- **Caching**: `exchange_rates.py` caches the ECB CSV in your temp directory for 24 hours.
- **Breakpoints**: There are `breakpoint()` calls in `create_json.py` (both in `evaluate_applicant` and `LLM_eval`) useful for debugging. Remove or comment them out for non-interactive/automation runs.
- **Airtable formulas**: Filtering by `Applicant` uses a formula in `create_json.py`. If `Applicant` is a linked-record field, you may prefer a formula like `FIND("<record_id>", ARRAYJOIN({Applicant}))` depending on your base setup.

### Troubleshooting

- **No records returned from related tables**
  - Verify the `Applicant` links are set correctly in `Personal Details`, `Work Experience`, and `Salary Preferences`.
  - If you store an Applicant ID string rather than a link, align the filtering formula accordingly.

- **Currency conversion errors**
  - Ensure the currency code in `Salary Preferences.Currency` is a valid ISO code supported by the ECB dataset.
  - If running offline, disable caching or clear the temp file to force a fresh download.

- **LLM errors or timeouts**
  - Confirm `OPENAI_API_KEY` is set and valid.
  - The model name in code is `gpt-5`. If not available to your account, update to a model you have access to.

### Credits

`exchange_rates.py` is adapted from and credits: `https://github.com/ddofborg/exchange_rates` and uses the [ECB eurofxref history](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip).