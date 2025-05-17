"""
ZappBot utils module
Contains helper functions for email, MongoDB, LLM, and parsing
"""

import re
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import openai

# MongoDB connection
def get_mongo_client() -> MongoClient:
    """Get MongoDB client instance from configuration in st.secrets"""
    mongo_cfg = {
        "host": "notify.pesuacademy.com",
        "port": 27017,
        "username": "admin",
        "password": st.secrets["MONGO_PASS"],
        "authSource": "admin",
    }
    return MongoClient(**mongo_cfg)

# Email formatting
def reformat_email_body(llm_output, intro="", conclusion=""):
    """
    Formats LLM output (list of dicts, dict, or string) as neat plain text for emails.
    
    Args:
        llm_output: string, dict, or list of dicts (parsed if possible)
        intro, conclusion: optional strings to prepend/append
        
    Returns:
        Formatted email body as string
    """
    lines = []
    # Try parsing JSON if LLM gave a JSON string
    if isinstance(llm_output, str):
        llm_output = llm_output.strip()
        # Try to parse if JSON-like
        try:
            parsed = json.loads(llm_output)
            llm_output = parsed
        except Exception:
            pass

    if intro:
        lines.append(intro.strip() + "\n")

    # Handle list of dicts (resumes, counts, etc)
    if isinstance(llm_output, list) and llm_output and isinstance(llm_output[0], dict):
        for i, item in enumerate(llm_output, 1):
            lines.append(f"Item {i}")
            lines.append("-" * 30)
            for k, v in item.items():
                lines.append(f"{k.capitalize():<15}: {v}")
            lines.append("")
    # Handle dict (summary data)
    elif isinstance(llm_output, dict):
        for k, v in llm_output.items():
            lines.append(f"{k.capitalize():<20}: {v}")
        lines.append("")
    # Handle string (or anything else)
    else:
        lines.append(str(llm_output).strip())
        lines.append("")

    if conclusion:
        lines.append(conclusion.strip())
    lines.append("\nSent by ZappBot")

    return "\n".join(lines)

# LLM-based scoring
def score_resumes(query: str, resumes: List[Dict[str, Any]], model_name: str, openai_api_key: str) -> List[str]:
    """
    Use LLM to score and rank resumes based on query.
    
    Args:
        query: Query string to match against resumes
        resumes: List of resume dictionaries to score
        model_name: OpenAI model name to use
        openai_api_key: OpenAI API key
        
    Returns:
        List of resumeIds ranked by relevance
    """
    from prompts import EVALUATOR_PROMPT
    
    openai_client = openai.OpenAI(api_key=openai_api_key)
    
    chat = openai_client.chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EVALUATOR_PROMPT},
            {"role": "user", "content": f"Query: {query}\n\nResumes: {json.dumps(resumes)}"},
        ],
    )
    content = json.loads(chat.choices[0].message.content)
    return content.get("top_resume_ids", [])

# Resume response parsing
def extract_resume_ids_from_response(response_text):
    """
    Extract resumeIds from the HTML comment in the response.
    
    Args:
        response_text: Text of response to extract from
        
    Returns:
        Dictionary mapping candidate names to resumeIds
    """
    meta_pattern = r'<!--RESUME_META:(.*?)-->'
    meta_match = re.search(meta_pattern, response_text)
    if meta_match:
        try:
            meta_data = json.loads(meta_match.group(1))
            return {item.get("name"): item.get("resumeId") for item in meta_data if item.get("resumeId")}
        except:
            return {}
    return {}

def process_response(text):
    """
    Process the response text to extract intro, resumes, and conclusion.
    
    Args:
        text: Text of response to process
        
    Returns:
        Dictionary with extracted components
    """
    # First, check if this is a resume-listing response
    if "Here are some" in text and ("Experience:" in text or "experience:" in text) and ("Skills:" in text or "skills:" in text):
        # Find the introductory text (everything before the first name)
        # Look for pattern of a blank line followed by a name (text with no indentation)
        intro_pattern = r'^(.*?)\n\n([A-Z][a-z]+.*?)\n\nEmail:'
        intro_match = re.search(intro_pattern, text, re.DOTALL)
        
        intro_text = ""
        if intro_match:
            intro_text = intro_match.group(1).strip()
        
        # Extract the resumes - accommodate both formats (numbered and unnumbered)
        # First try standard format with blank lines
        resume_pattern = r'([A-Z][a-z]+ (?:[A-Z][a-z]+ )?(?:[A-Z][a-z]+)?)\s*\n\s*Email:\s*([^\n]+)\s*\nContact No:\s*([^\n]+)\s*\nLocation:\s*([^\n]+)\s*\nExperience:\s*([^\n]+)\s*\nSkills:\s*([^\n]+)'
        matches = re.findall(resume_pattern, text, re.MULTILINE | re.IGNORECASE)
        
        # If that didn't work, try the numbered format
        if not matches:
            resume_pattern = r'\d+\.\s+\*\*([^*]+)\*\*\s*\n\s*-\s+\*\*Email:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Contact No:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Location:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Experience:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Skills:\*\*\s+([^\n]+)'
            matches = re.findall(resume_pattern, text, re.MULTILINE)
        
        # Extract the conclusion (after all resumes)
        # Look for lines that contain phrases like "These candidates" or similar conclusion statements
        conclusion_pattern = r'(These candidates.*?)\s*$'
        conclusion_match = re.search(conclusion_pattern, text, re.DOTALL)
        
        conclusion_text = ""
        if conclusion_match:
            conclusion_text = conclusion_match.group(1).strip()
        
        # Convert resume matches to structured data
        resumes = []
        for match in matches:
            name, email, contact, location, experience, skills = match
            
            # Split skills and experience
            skill_list = [s.strip() for s in skills.split(',')]
            exp_list = [e.strip() for e in experience.split(',')]
            
            resumes.append({
                "name": name.strip(),
                "email": email.strip(),
                "contactNo": contact.strip(),
                "location": location.strip(),
                "experience": exp_list,
                "skills": skill_list,
                "keywords": []  # Initialize empty keywords list; will be populated when we retrieve from DB
            })
        
        return {
            "is_resume_response": True,
            "intro_text": intro_text,
            "resumes": resumes,
            "conclusion_text": conclusion_text,
            "full_text": text  # Keep this for debug purposes
        }
    else:
        # Not a resume listing response
        return {
            "is_resume_response": False,
            "full_text": text
        }

def attach_hidden_resume_ids(resume_list: List[Dict[str, Any]], db_name="resumes_database", coll_name="resumes") -> None:
    """
    For every resume in resume_list that lacks a 'resumeId', look it up by (email, contactNo)
    and add it. Also fetches keywords.
    
    Args:
        resume_list: List of resume dictionaries to enhance
        db_name: MongoDB database name
        coll_name: MongoDB collection name
    """
    if not resume_list:
        return
    
    with get_mongo_client() as client:
        coll = client[db_name][coll_name]
        for res in resume_list:
            email = res.get("email")
            phone = res.get("contactNo")
            if email and phone:
                doc = coll.find_one(
                    {"email": email, "contactNo": phone},
                    {"_id": 0, "resumeId": 1, "keywords": 1},
                )
                if doc:
                    if doc.get("resumeId"):
                        res["resumeId"] = doc["resumeId"]
                    if doc.get("keywords"):
                        res["keywords"] = doc["keywords"]
