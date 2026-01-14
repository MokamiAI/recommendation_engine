from fastapi import FastAPI, HTTPException

# -----------------------------
# SCRAPING (company-name based)
# -----------------------------
from scraper.company_name_scraper import scrape_by_company_name

# -----------------------------
# INGESTION
# -----------------------------
from app.schemas.ingestion import RawProductIn
from app.normalizers.product_normalizer import normalize_product
from app.normalizers.feature_extractor import extract_features
from app.repositories.company_repo import get_or_create_company
from app.repositories.product_repo import upsert_insurance_product
from app.repositories.features_repo import insert_features

# -----------------------------
# NEEDS-BASED RECOMMENDATION
# -----------------------------
from app.schemas.profile import UserProfile
from app.recommendation.needs_engine import recommend_policies


app = FastAPI(
    title="Insurance Recommendation Engine",
    version="1.0.0"
)

# --------------------------------------------------
# HEALTH
# --------------------------------------------------
@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# MANUAL INGESTION (OPTIONAL)
# --------------------------------------------------
@app.post("/ingest-raw")
def ingest_raw_product(raw: RawProductIn):
    try:
        normalized = normalize_product(raw.dict())
        features = extract_features(raw.raw_text)

        company_id = get_or_create_company(raw.company_name)

        product_id = upsert_insurance_product(
            company_id=company_id,
            product=normalized
        )

        insert_features(product_id, features)

        return {
            "status": "ingested",
            "product_id": product_id,
            "features_created": len(features)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# 🔍 SCRAPE USING COMPANY NAMES (PRIMARY PIPELINE)
# --------------------------------------------------
@app.post("/scrape-by-company-name")
def scrape_using_company_names():
    """
    1. Fetch active companies from DB
    2. Search public web pages using company names
    3. Scrape product data
    4. Normalize & store in DB
    """

    payloads = scrape_by_company_name()
    results = []

    for payload in payloads:

        if "error" in payload:
            results.append(payload)
            continue

        try:
            normalized = normalize_product(payload)
            features = extract_features(payload["raw_text"])

            company_id = get_or_create_company(payload["company_name"])

            product_id = upsert_insurance_product(
                company_id=company_id,
                product=normalized
            )

            insert_features(product_id, features)

            results.append({
                "company_name": payload["company_name"],
                "product_id": product_id,
                "source_url": payload.get("product_page_url")
            })

        except Exception as e:
            results.append({
                "company_name": payload.get("company_name"),
                "error": str(e)
            })

    return {
        "status": "completed",
        "items_processed": len(results),
        "results": results
    }


# --------------------------------------------------
# 🎯 NEEDS-BASED RECOMMENDATION (THIS IS THE CORRECT ONE)
# --------------------------------------------------
@app.post("/recommend-by-profile")
def recommend_by_profile(profile: UserProfile):
    """
    Needs-based insurance recommendation.
    The user does NOT choose products.
    The system determines what insurance is required.
    """

    recommendations = recommend_policies(profile.dict())

    return {
        "profile_summary": {
            "age": profile.age,
            "monthly_income": profile.monthly_income,
            "dependants": profile.dependants,
            "employment_type": profile.employment_type,
            "owns_car": profile.owns_car,
            "owns_home": profile.owns_home
        },
        "recommended_policies": recommendations
    }
