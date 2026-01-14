from fastapi import FastAPI, HTTPException

# Ingestion
from app.schemas.ingestion import RawProductIn
from app.normalizers.product_normalizer import normalize_product
from app.normalizers.feature_extractor import extract_features
from app.repositories.company_repo import get_or_create_company
from app.repositories.product_repo import upsert_insurance_product
from app.repositories.features_repo import insert_features
from app.scraper import scrape_all_companies_from_db

# Recommendation
from app.schemas.recommendation import (
    RecommendationRequest,
    RecommendationResponse,
    RecommendationItem
)
from app.repositories.recommendation_repo import fetch_candidate_products
from app.recommendation.engine import score_product


app = FastAPI(
    title="Insurance Recommendation Engine",
    version="1.0.0"
)


# --------------------------------------------------
# Health
# --------------------------------------------------
@app.get("/")
def root():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# Manual ingestion
# --------------------------------------------------
@app.post("/ingest-raw")
def ingest_raw_product(raw: RawProductIn):

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


# --------------------------------------------------
# DB-driven scraping
# --------------------------------------------------
@app.post("/scrape-from-db")
def scrape_from_database():

    payloads = scrape_all_companies_from_db()
    results = []

    for payload in payloads:

        if "error" in payload:
            results.append(payload)
            continue

        normalized = normalize_product(payload)
        features = extract_features(payload["raw_text"])

        product_id = upsert_insurance_product(
            company_id=payload["company_id"],
            product=normalized
        )

        insert_features(product_id, features)

        results.append({
            "company_name": payload["company_name"],
            "product_id": product_id,
            "features_created": len(features)
        })

    return {
        "status": "completed",
        "companies_processed": len(payloads),
        "results": results
    }


# --------------------------------------------------
# 🎯 RECOMMENDATION ENGINE
# --------------------------------------------------
@app.post("/recommend", response_model=RecommendationResponse)
def recommend_products(request: RecommendationRequest):

    products = fetch_candidate_products(request.product_category)

    if not products:
        return {"recommendations": []}

    scored = []

    for product in products:
        result = score_product(product, request.dict())

        if result["score"] > 0:
            scored.append({
                "product_id": product["product_id"],
                "company_name": product["company_name"],
                "product_name": product["product_name"],
                "premium_estimate": product.get("premium_min") or 0,
                "score": result["score"],
                "reasons": result["reasons"]
            })

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "recommendations": scored[:5]
    }
