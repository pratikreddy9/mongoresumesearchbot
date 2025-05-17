import os
from typing import List, Optional, Dict, Any

import streamlit as st
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from langchain_core.tools import tool
from pymongo.errors import PyMongoError
import openai
import json

from utils import get_mongo_client, score_resumes
from variants import expand, COUNTRY_EQUIV, SKILL_VARIANTS, TITLE_VARIANTS

# Constants
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
SMTP_USER, SMTP_PASS = st.secrets["SMTP_USER"], st.secrets["SMTP_PASS"]
EVAL_MODEL_NAME = "gpt-4o" 
TOP_K_DEFAULT = 100
DB_NAME = "resumes_database"
COLL_NAME = "resumes"

# Initialize OpenAI client
_openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

@tool
def query_db(
    query: str,
    country: Optional[str] = None,
    min_experience_years: Optional[int] = None,
    max_experience_years: Optional[int] = None,
    job_titles: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    top_k: int = TOP_K_DEFAULT,
) -> Dict[str, Any]:
    """Filter MongoDB resumes and return top matches using a two-stage process."""
    try:
        # STAGE 1: Get initial candidates from MongoDB with basic filtering
        # This casts a wider net to find potential matches
        mongo_q: Dict[str, Any] = {}
        and_conditions = []
        
        # Country filter (if provided)
        if country:
            mongo_q["country"] = {"$in": COUNTRY_EQUIV.get(country.strip().lower(), [country])}
        
        # Skills filter - using AND logic between different skills, but OR between variants
        if skills and len(skills) > 0:
            skill_conditions = []
            for skill in skills:
                # Expand variants for this specific skill
                expanded = expand([skill], SKILL_VARIANTS)
                # Create OR condition between skill name and keywords for this skill and its variants
                skill_conditions.append({
                    "$or": [
                        {"skills.skillName": {"$in": expanded}},
                        {"keywords": {"$in": expanded}}
                    ]
                })
            # Add all skill conditions with AND logic
            and_conditions.extend(skill_conditions)
        
        # Job titles filter - using AND logic between different titles, but OR between variants
        if job_titles and len(job_titles) > 0:
            title_conditions = []
            for title in job_titles:
                # Expand variants for this specific title
                expanded = expand([title], TITLE_VARIANTS)
                # Create OR condition for this title and its variants
                title_conditions.append({
                    "jobExperiences.title": {"$in": expanded}
                })
            # Add all title conditions with AND logic
            and_conditions.extend(title_conditions)
        
        # Experience filter - using totalExperience field if available, otherwise sum job durations
        # This handles both cases where totalExperience is available or we need to calculate from durations
        if isinstance(min_experience_years, (int, float)) and min_experience_years > 0:
            experience_condition = {
                "$or": [
                    # First try using the totalExperience field if it exists and is not null
                    {"totalExperience": {"$gte": min_experience_years}},
                    # Fallback: use $expr to calculate total from job durations 
                    {"$expr": {
                        "$gte": [
                            {"$sum": {
                                "$map": {
                                    "input": "$jobExperiences",
                                    "as": "job",
                                    "in": {
                                        "$convert": {
                                            "input": "$job.duration",
                                            "to": "double",
                                            "onError": 0,
                                            "onNull": 0
                                        }
                                    }
                                }
                            }},
                            min_experience_years
                        ]
                    }}
                ]
            }
            and_conditions.append(experience_condition)
        
        if isinstance(max_experience_years, (int, float)) and max_experience_years > 0:
            experience_condition = {
                "$or": [
                    # First try using the totalExperience field if it exists and is not null
                    {"totalExperience": {"$lte": max_experience_years}},
                    # Fallback: use $expr to calculate total from job durations
                    {"$expr": {
                        "$lte": [
                            {"$sum": {
                                "$map": {
                                    "input": "$jobExperiences",
                                    "as": "job",
                                    "in": {
                                        "$convert": {
                                            "input": "$job.duration",
                                            "to": "double",
                                            "onError": 0,
                                            "onNull": 0
                                        }
                                    }
                                }
                            }},
                            max_experience_years
                        ]
                    }}
                ]
            }
            and_conditions.append(experience_condition)
        
        # Add the AND conditions to the query if there are any
        if and_conditions:
            mongo_q["$and"] = and_conditions
        
        # Get initial candidates from MongoDB
        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            debug_mode = getattr(st.session_state, 'debug_mode', False)
            if debug_mode:
                print(f"MongoDB Query: {json.dumps(mongo_q, indent=2)}")
            
            # Get a larger initial candidate pool to let the LLM select from
            candidates = list(coll.find(mongo_q, {"_id": 0, "embedding": 0}).limit(50))
        
        # STAGE 2: Use LLM to strictly filter and score candidates
        # This ensures candidates meet ALL criteria, not just some
        
        # If no candidates found in initial search, return empty results
        if not candidates:
            return {
                "message": "No resumes match the criteria.",
                "results_count": 0,
                "results": [],
                "completed_at": datetime.utcnow().isoformat(),
            }
        
        # Create a prompt that strictly enforces ALL criteria
        system_prompt = f"""
        You are a strict resume evaluator. Your task is to identify candidates 
        that meet ALL of the following criteria from the query:
        
        QUERY: {query}
        
        Criteria to enforce STRICTLY:
        1. Job Title: Must have held a job title of "software developer" or very 
           close variants like "software engineer". Having skills is NOT enough.
        
        2. Experience: Must have at least {min_experience_years if min_experience_years else "the required"} 
           years of experience specifically in developer roles.
        
        3. Skills: Must have ALL the specific skills mentioned in the query.
        
        4. Location: Must be in {country if country else "the specified location"}.
        
        Return ONLY resumeIds of candidates who meet ALL criteria. It's better to 
        return fewer excellent matches than many poor matches.
        
        Format your response as JSON:
        {{
          "top_resume_ids": [...], 
          "reasoning": "brief explanation of why these candidates match"
        }}
        """
        
        # Use LLM to evaluate candidates against strict criteria
        chat = _openai_client.chat.completions.create(
            model=EVAL_MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Candidates: {json.dumps(candidates)}"},
            ],
        )
        
        # Parse LLM response
        try:
            content = json.loads(chat.choices[0].message.content)
            best_ids = content.get("top_resume_ids", [])
            reasoning = content.get("reasoning", "")
        except Exception as e:
            return {"error": f"Error parsing LLM response: {str(e)}"}
        
        # Get the best candidates using the IDs from the LLM
        best_resumes = [r for r in candidates if r["resumeId"] in best_ids]
        
        return {
            "message": f"Found {len(best_resumes)} resumes that meet ALL criteria out of {len(candidates)} initial matches.",
            "results_count": len(best_resumes),
            "results": best_resumes,
            "reasoning": reasoning,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except PyMongoError as err:
        return {"error": f"DB error: {str(err)}"}
    except Exception as exc:
        return {"error": str(exc)}


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain text email using SMTP_USER / SMTP_PASS from secrets.toml."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, to
        # Plain text email only
        msg.attach(MIMEText(body, "plain"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as srv:
            srv.login(SMTP_USER, SMTP_PASS)
            srv.send_message(msg)
        return "Email sent!"
    except Exception as e:
        return f"Email failed: {e}"


@tool
def get_job_match_counts(resume_ids: List[str]) -> Dict[str, Any]:
    """
    Given a list of resumeIds, return how many unique jobIds each resume is
    matched to in the resume_matches collection.
    """
    try:
        if not isinstance(resume_ids, list):
            return {"error": "resume_ids must be a list of strings"}
        results = []
        with get_mongo_client() as client:
            coll = client[DB_NAME]["resume_matches"]
            for rid in resume_ids:
                doc = coll.find_one({"resumeId": rid}, {"_id": 0, "matches.jobId": 1})
                jobs = doc.get("matches", []) if doc else []
                results.append({"resumeId": rid, "jobsMatched": len(jobs)})
        return {
            "message": f"Counts fetched for {len(results)} resumeIds.",
            "results_count": len(results),
            "results": results,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except PyMongoError as err:
        return {"error": f"DB error: {str(err)}"}
    except Exception as exc:
        return {"error": str(exc)}


@tool
def get_resume_id_by_name(name: str) -> Dict[str, Any]:
    """
    Given a candidate name, return their resumeId if it exists in our records.
    """
    try:
        if "resume_ids" not in st.session_state:
            return {"error": "No resume IDs are stored in the current session."}
        
        # Normalize name by lowercasing and removing extra spaces
        name_norm = ' '.join(name.lower().split())
        
        # Try exact match first
        if name_norm in [k.lower() for k in st.session_state.resume_ids.keys()]:
            for k, v in st.session_state.resume_ids.items():
                if k.lower() == name_norm:
                    return {
                        "found": True, 
                        "name": k, 
                        "resumeId": v
                    }
        
        # Try partial match
        for k, v in st.session_state.resume_ids.items():
            if name_norm in k.lower():
                return {
                    "found": True, 
                    "name": k, 
                    "resumeId": v
                }
        
        # If no match found in session state, try database lookup
        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            # Try to find by name
            query = {"$or": [
                {"name": {"$regex": name, "$options": "i"}},
                {"fullName": {"$regex": name, "$options": "i"}}
            ]}
            doc = coll.find_one(query, {"_id": 0, "resumeId": 1, "name": 1, "fullName": 1})
            if doc and doc.get("resumeId"):
                display_name = doc.get("name") or doc.get("fullName") or name
                return {
                    "found": True,
                    "name": display_name,
                    "resumeId": doc["resumeId"]
                }
        
        return {"found": False, "message": f"No resumeId found for '{name}'"}
    except Exception as e:
        return {"error": str(e)}
