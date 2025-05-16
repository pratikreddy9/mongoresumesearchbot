import streamlit as st
import os, json, re
from pymongo import MongoClient
from typing import List, Dict, Any, Optional

# Configuration
st.set_page_config(page_title="Resume Search Tester", layout="wide")

# MongoDB connection settings
# You can replace these with your actual credentials or use secrets
MONGO_CFG = {
    "host": "notify.pesuacademy.com",
    "port": 27017,
    "username": "admin",
    "password": st.secrets["MONGO_PASS"] if "MONGO_PASS" in st.secrets else "",
    "authSource": "admin",
}
DB_NAME = "resumes_database"
COLL_NAME = "resumes"
TOP_K_DEFAULT = 50

# --- Only keep country variants map ---
COUNTRY_EQUIV = {
    "indonesia": ["indonesia"],
    "vietnam": ["vietnam", "viet nam", "vn", "vietnamese"],
    "united states": ["united states", "usa", "us"],
    "malaysia": ["malaysia"],
    "india": ["india", "ind"],
    "singapore": ["singapore"],
    "philippines": ["philippines", "the philippines"],
    "australia": ["australia"],
    "new zealand": ["new zealand"],
    "germany": ["germany"],
    "saudi arabia": ["saudi arabia", "ksa"],
    "japan": ["japan"],
    "hong kong": ["hong kong", "hong kong sar"],
    "thailand": ["thailand"],
    "united arab emirates": ["united arab emirates", "uae"],
}

# --- Helper Functions ---
def get_mongo_client() -> MongoClient:
    """Create and return a MongoDB client."""
    return MongoClient(**MONGO_CFG)

def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, removing extra spaces and special characters."""
    if not text or not isinstance(text, str):
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Handle special characters for programming languages
    text = text.replace("c#", "csharp")
    text = text.replace("c++", "cplusplus")
    text = text.replace("c/c++", "c cplusplus")
    text = text.replace(".net", "dotnet")
    
    # Remove dots from abbreviations
    text = text.replace(".", "")
    
    # Handle common variations
    text = text.replace("javascript", "js")
    text = text.replace("typescript", "ts")
    text = text.replace("python", "py")
    
    return text

def search_resumes(
    query_text: str,
    country: Optional[str] = None,
    min_experience_years: Optional[int] = None,
    job_titles: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    search_method: str = "basic",
    top_k: int = TOP_K_DEFAULT,
) -> Dict[str, Any]:
    """
    Search for resumes in MongoDB with improved normalization and different AND logic approaches.
    
    Args:
        query_text: Raw query text (for reference only)
        country: Country filter
        min_experience_years: Minimum years of experience
        job_titles: List of job titles to search for
        skills: List of skills to search for
        search_method: Which search method to use (strict, relaxed, balanced)
        top_k: Maximum number of results to return
        
    Returns:
        Dictionary with search results and metadata
    """
    try:
        # Connect to MongoDB
        mongo_q = {}
        and_conditions = []
        
        # Country filter (always applied if provided)
        if country:
            country_values = COUNTRY_EQUIV.get(country.strip().lower(), [country])
            
            # We'll allow both exact match and case-insensitive matches
            country_condition = {
                "$or": [
                    {"country": {"$in": country_values}},
                    {"country": {"$regex": f"^{re.escape(country)}$", "$options": "i"}}
                ]
            }
            and_conditions.append(country_condition)
        
        # Experience filter (always applied if provided)
        if isinstance(min_experience_years, int) and min_experience_years > 0:
            and_conditions.append({
                "$expr": {
                    "$gte": [
                        # Sum all job durations, converting to numbers and handling null/missing values
                        {"$sum": {
                            "$map": {
                                "input": {"$ifNull": ["$jobExperiences", []]},
                                "as": "job",
                                "in": {
                                    "$convert": {
                                        "input": {"$ifNull": ["$$job.duration", "0"]},
                                        "to": "double",
                                        "onError": 0,
                                        "onNull": 0
                                    }
                                }
                            }
                        }},
                        min_experience_years
                    ]
                }
            })
        
        # Job titles and skills are applied differently based on search method
        if search_method == "strict":
            # Strict: All job titles AND all skills must match exactly
            
            # Job title filter (if provided)
            if job_titles and len(job_titles) > 0:
                # For each job title, create a condition that it appears in at least one job
                for title in job_titles:
                    if not title:
                        continue
                    title_condition = {
                        "jobExperiences.title": {
                            "$regex": f"\\b{re.escape(title.lower())}\\b", 
                            "$options": "i"  # Case insensitive
                        }
                    }
                    and_conditions.append(title_condition)
            
            # Skills filter (if provided) - ALL skills must be present
            if skills and len(skills) > 0:
                for skill in skills:
                    if not skill:
                        continue
                        
                    # Each skill must be present in either skills.skillName OR keywords
                    skill_condition = {
                        "$or": [
                            {
                                "skills.skillName": {
                                    "$regex": f"\\b{re.escape(skill.lower())}\\b", 
                                    "$options": "i"  # Case insensitive
                                }
                            },
                            {
                                "keywords": {
                                    "$regex": f"\\b{re.escape(skill.lower())}\\b", 
                                    "$options": "i"  # Case insensitive
                                }
                            }
                        ]
                    }
                    and_conditions.append(skill_condition)
                
        elif search_method == "relaxed":
            # Relaxed: At least one job title AND at least one skill must match
            
            # Job title filter (if provided)
            if job_titles and len(job_titles) > 0:
                title_conditions = []
                for title in job_titles:
                    if not title:
                        continue
                    title_conditions.append({
                        "jobExperiences.title": {
                            "$regex": f"\\b{re.escape(title.lower())}\\b", 
                            "$options": "i"  # Case insensitive
                        }
                    })
                
                if title_conditions:
                    # At least one job title must match
                    and_conditions.append({"$or": title_conditions})
            
            # Skills filter (if provided) - at least ONE skill must be present
            if skills and len(skills) > 0:
                skill_conditions = []
                for skill in skills:
                    if not skill:
                        continue
                    
                    # Each skill can be in either skills.skillName OR keywords
                    skill_conditions.append({
                        "skills.skillName": {
                            "$regex": f"\\b{re.escape(skill.lower())}\\b", 
                            "$options": "i"
                        }
                    })
                    skill_conditions.append({
                        "keywords": {
                            "$regex": f"\\b{re.escape(skill.lower())}\\b", 
                            "$options": "i"
                        }
                    })
                
                if skill_conditions:
                    # At least one skill must match
                    and_conditions.append({"$or": skill_conditions})
                
        elif search_method == "balanced":
            # Balanced: At least one job title AND all skills in skill groups must match
            
            # Job title filter (if provided)
            if job_titles and len(job_titles) > 0:
                title_conditions = []
                for title in job_titles:
                    if not title:
                        continue
                    title_conditions.append({
                        "jobExperiences.title": {
                            "$regex": f"\\b{re.escape(title.lower())}\\b", 
                            "$options": "i"  # Case insensitive
                        }
                    })
                
                if title_conditions:
                    # At least one job title must match
                    and_conditions.append({"$or": title_conditions})
            
            # Skills filter (if provided) - Group skills into categories
            if skills and len(skills) > 0:
                # Group skills by "type" - for example SQL variants
                sql_variants = []
                python_variants = []
                javascript_variants = []
                other_skills = []
                
                for skill in skills:
                    if not skill:
                        continue
                        
                    skill_lower = skill.lower()
                    
                    if any(term in skill_lower for term in ["sql", "mysql", "postgresql", "nosql"]):
                        sql_variants.append(skill_lower)
                    elif any(term in skill_lower for term in ["python", "py", "django", "flask"]):
                        python_variants.append(skill_lower)
                    elif any(term in skill_lower for term in ["javascript", "js", "typescript", "node"]):
                        javascript_variants.append(skill_lower)
                    else:
                        other_skills.append(skill_lower)
                
                # For each skill category, require at least one match
                skill_groups = [
                    (sql_variants, "SQL"),
                    (python_variants, "Python"),
                    (javascript_variants, "JavaScript"),
                ]
                
                for variants, group_name in skill_groups:
                    if variants:
                        # Create conditions for this skill group
                        group_conditions = []
                        for variant in variants:
                            group_conditions.append({
                                "skills.skillName": {
                                    "$regex": f"\\b{re.escape(variant)}\\b", 
                                    "$options": "i"
                                }
                            })
                            group_conditions.append({
                                "keywords": {
                                    "$regex": f"\\b{re.escape(variant)}\\b", 
                                    "$options": "i"
                                }
                            })
                        
                        # At least one variant in this group must match
                        and_conditions.append({
                            "$or": group_conditions
                        })
                
                # For other skills, each must be present
                for skill in other_skills:
                    skill_condition = {
                        "$or": [
                            {
                                "skills.skillName": {
                                    "$regex": f"\\b{re.escape(skill)}\\b", 
                                    "$options": "i"
                                }
                            },
                            {
                                "keywords": {
                                    "$regex": f"\\b{re.escape(skill)}\\b", 
                                    "$options": "i"
                                }
                            }
                        ]
                    }
                    and_conditions.append(skill_condition)
        
        # Combine all AND conditions
        if and_conditions:
            mongo_q["$and"] = and_conditions
        
        # Execute the query
        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            
            # Find candidates matching the criteria
            candidates = list(coll.find(mongo_q, {"_id": 0}).limit(top_k))
            
            # Get a sample document structure if available
            sample_structure = None
            if candidates:
                sample = candidates[0]
                sample_structure = {
                    "fields": list(sample.keys()),
                    "jobExperiences": sample.get("jobExperiences", [])[:1] if "jobExperiences" in sample else None,
                    "skills": sample.get("skills", [])[:3] if "skills" in sample else None,
                    "keywords": sample.get("keywords", [])[:3] if "keywords" in sample else None,
                    "country": sample.get("country", None)
                }
        
        # Return the results
        return {
            "query": mongo_q,
            "count": len(candidates),
            "candidates": candidates,
            "sample_structure": sample_structure
        }
    
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "query": mongo_q if 'mongo_q' in locals() else None
        }

# --- Streamlit UI ---
st.title("Resume Search Tester")
st.write("This app lets you test the resume search functionality and see the raw MongoDB results.")

# Search form
with st.form("search_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        query_text = st.text_input("Raw Query Text (for reference only)", 
                                   "Find software developer in Indonesia with SQL and Python skills")
        country = st.text_input("Country", "Indonesia")
        min_exp = st.number_input("Minimum Experience (years)", min_value=0, value=3, step=1)
    
    with col2:
        job_titles_input = st.text_input("Job Titles (comma-separated)", "software developer")
        job_titles = [t.strip() for t in job_titles_input.split(",")] if job_titles_input else []
        
        skills_input = st.text_input("Skills (comma-separated)", "SQL, Python")
        skills = [s.strip() for s in skills_input.split(",")] if skills_input else []
        
        search_method = st.selectbox(
            "Search Method", 
            ["strict", "balanced", "relaxed"],
            format_func=lambda x: {
                "strict": "Strict (ALL skills + ALL job titles)",
                "balanced": "Balanced (At least one job title + skill category matching)",
                "relaxed": "Relaxed (At least one job title + at least one skill)"
            }.get(x, x)
        )
    
    submit_button = st.form_submit_button("Search Resumes")

# Execute search when form is submitted
if submit_button:
    with st.spinner("Searching..."):
        results = search_resumes(
            query_text=query_text,
            country=country,
            min_experience_years=min_exp,
            job_titles=job_titles,
            skills=skills,
            search_method=search_method
        )
    
    # Display results
    if "error" in results:
        st.error(f"Error: {results['error']}")
        st.code(results["traceback"])
    else:
        st.success(f"Found {results['count']} matching resumes")
        
        # Show the MongoDB query
        with st.expander("MongoDB Query", expanded=True):
            st.code(json.dumps(results["query"], indent=2))
        
        # Show sample document structure
        if results["sample_structure"]:
            with st.expander("Sample Document Structure", expanded=True):
                st.json(results["sample_structure"])
        
        # Calculate total experience for each candidate
        candidates_with_total_exp = []
        for candidate in results["candidates"]:
            # Calculate total experience
            total_exp = 0
            job_exp = candidate.get("jobExperiences", [])
            for job in job_exp:
                try:
                    duration = job.get("duration", "0")
                    if duration:
                        total_exp += float(duration)
                except (ValueError, TypeError):
                    pass
            
            # Check if candidate has the required skills
            has_required_skills = True
            if skills:
                candidate_skills = set()
                for skill in candidate.get("skills", []):
                    if isinstance(skill, dict) and skill.get("skillName"):
                        candidate_skills.add(skill["skillName"].lower())
                candidate_skills.update([k.lower() for k in candidate.get("keywords", [])])
                
                # Check for required skills
                for req_skill in skills:
                    req_skill_lower = req_skill.lower()
                    # Simple check for now - more sophisticated matching would be better
                    if not any(req_skill_lower in s for s in candidate_skills):
                        has_required_skills = False
                        break
            
            # Add to list
            candidates_with_total_exp.append({
                "candidate": candidate,
                "total_experience": total_exp,
                "has_required_skills": has_required_skills
            })
        
        # Sort by total experience (descending) and skill match
        candidates_with_total_exp.sort(key=lambda x: (x["has_required_skills"], x["total_experience"]), reverse=True)
        
        # Show the raw results
        with st.expander(f"Raw Results ({results['count']} records)", expanded=False):
            st.json(results["candidates"])
        
        # Display candidates in a more readable format
        st.subheader("Matching Candidates")
        
        for i, item in enumerate(candidates_with_total_exp):
            candidate = item["candidate"]
            total_exp = item["total_experience"]
            has_skills = item["has_required_skills"]
            
            skill_match_icon = "✅" if has_skills else "❌"
            
            with st.expander(f"Candidate {i+1}: {candidate.get('name', 'Unknown')} - {total_exp} years - Skills: {skill_match_icon}"):
                # Basic information
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Name:** {candidate.get('name', 'N/A')}")
                    st.write(f"**Email:** {candidate.get('email', 'N/A')}")
                    st.write(f"**Contact:** {candidate.get('contactNo', 'N/A')}")
                    st.write(f"**Country:** {candidate.get('country', 'N/A')}")
                    st.write(f"**Total Experience:** {total_exp} years")
                    st.write(f"**ResumeId:** {candidate.get('resumeId', 'N/A')}")
                
                # Job experience
                st.write("**Job Experience:**")
                job_exp = candidate.get("jobExperiences", [])
                if job_exp:
                    for job in job_exp:
                        st.write(f"- {job.get('title', 'N/A')} ({job.get('duration', 'N/A')} years)")
                else:
                    st.write("- No job experience found")
                
                # Skills
                st.write("**Skills:**")
                skills_list = candidate.get("skills", [])
                if skills_list:
                    skill_text = ""
                    for skill in skills_list:
                        if isinstance(skill, dict):
                            skill_text += f"- {skill.get('skillName', 'N/A')}\n"
                        else:
                            skill_text += f"- {skill}\n"
                    st.text(skill_text)
                else:
                    st.write("- No skills found")
                
                # Keywords
                st.write("**Keywords:**")
                keywords = candidate.get("keywords", [])
                if keywords:
                    st.write(", ".join(keywords))
                else:
                    st.write("- No keywords found")
