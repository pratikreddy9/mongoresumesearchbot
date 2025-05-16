"""
ZappBot: Resume-filtering chatbot with optimized display + email sender + job match counts
LangChain 0.3.25 • OpenAI 1.78.1 • Streamlit 1.34+
"""

# Email imports
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import os, json, re, hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
import openai

# ── CONFIG ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# SMTP constants
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
SMTP_USER, SMTP_PASS = st.secrets["SMTP_USER"], st.secrets["SMTP_PASS"]

MONGO_CFG = {
    "host": "notify.pesuacademy.com",
    "port": 27017,
    "username": "admin",
    "password": st.secrets["MONGO_PASS"],
    "authSource": "admin",
}
MODEL_NAME = "gpt-4o"
EVAL_MODEL_NAME = "gpt-4o"
TOP_K_DEFAULT = 50
DB_NAME = "resumes_database"
COLL_NAME = "resumes"

# ── UNIVERSAL EMAIL FORMATTER ──────────────────────────────────────────
def reformat_email_body(llm_output, intro: str = "", conclusion: str = "") -> str:
    """
    Formats LLM output (list of dicts, dict, or string) as neat plain text for emails.
    """
    lines = []
    # Try to JSON-parse strings
    if isinstance(llm_output, str):
        try:
            llm_output = json.loads(llm_output.strip())
        except Exception:
            pass

    if intro:
        lines.append(intro.strip() + "\n")

    if isinstance(llm_output, list) and llm_output and isinstance(llm_output[0], dict):
        for i, item in enumerate(llm_output, 1):
            lines.append(f"Item {i}")
            lines.append("-" * 30)
            for k, v in item.items():
                lines.append(f"{k.capitalize():<15}: {v}")
            lines.append("")
    elif isinstance(llm_output, dict):
        for k, v in llm_output.items():
            lines.append(f"{k.capitalize():<20}: {v}")
        lines.append("")
    else:
        lines.append(str(llm_output).strip())
        lines.append("")

    if conclusion:
        lines.append(conclusion.strip())
    lines.append("\nSent by ZappBot")
    return "\n".join(lines)

# ── MONGO ──────────────────────────────────────────────────────────────
def get_mongo_client() -> MongoClient:
    return MongoClient(**MONGO_CFG)

# ── NORMALIZATION ──────────────────────────────────────────────────────
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

# ── SKILL / TITLE VARIANTS ────────────────────────────────────────────
SKILL_VARIANTS = {
    "sql": ["sql", "mysql", "postgresql", "mariadb", "t-sql", "microsoft sql server"],
    "python": ["python"],
    "javascript": ["javascript", "js", "java script"],
    "c#": ["c#", "c sharp", "csharp"],
    "html": ["html", "hypertext markup language"],
    # add more if needed…
}
TITLE_VARIANTS = {
    "software developer": [
        "software developer",
        "software dev",
        "softwaredeveloper",
        "software engineer",
    ],
    "backend developer": [
        "backend developer",
        "backend dev",
        "back-end developer",
        "server-side developer",
    ],
    "frontend developer": [
        "frontend developer",
        "frontend dev",
        "front-end developer",
    ],
}

def expand(values: List[str], table: Dict[str, List[str]]) -> List[str]:
    out: set[str] = set()
    for v in values:
        v_low = v.strip().lower()
        out.update(table.get(v_low, []))
        out.add(v)
    return list(out)

# ── LLM-BASED RESUME SCORER ────────────────────────────────────────────
_openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
EVALUATOR_PROMPT = """
You are a resume scoring assistant. Return only the 10 best resumeIds.

JSON format:
{
  "top_resume_ids": [...],
  "completed_at": "ISO"
}
"""
def score_resumes(query: str, resumes: List[Dict[str, Any]]) -> List[str]:
    chat = _openai_client.chat.completions.create(
        model=EVAL_MODEL_NAME,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EVALUATOR_PROMPT},
            {"role": "user", "content": f"Query: {query}\n\nResumes: {json.dumps(resumes)}"},
        ],
    )
    content = json.loads(chat.choices[0].message.content)
    return content.get("top_resume_ids", [])

# ── TOOLS ─────────────────────────────────────────────────────────────
@tool
def query_db(
    query: str = "",                       # ← give it a default so it’s no longer “required”
    country: Optional[str] = None,
    min_experience_years: Optional[int] = None,
    max_experience_years: Optional[int] = None,
    job_titles: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    top_k: int = TOP_K_DEFAULT,
) -> Dict[str, Any]:
    """
    Filter MongoDB resumes.  
    Loose OR inside each synonym bucket, strict AND across different skills.
    """
    try:
        if not query:
            # fall back to a simple human-readable query so the LLM re-ranker has something
            query = " / ".join(skills or []) or "resume search"

        mongo_q: Dict[str, Any] = {}
        and_clauses: List[Dict[str, Any]] = []

        # Country
        if country:
            mongo_q["country"] = {"$in": COUNTRY_EQUIV.get(country.strip().lower(), [country])}

        # Skills – build one $or clause per requested skill, then AND them all
        if skills:
            for skill in skills:
                synonyms = expand([skill], SKILL_VARIANTS)
                and_clauses.append(
                    {
                        "$or": [
                            {"skills.skillName": {"$in": synonyms}},
                            {"keywords": {"$in": synonyms}},
                        ]
                    }
                )

        # Job titles
        if job_titles:
            and_clauses.append(
                {"jobExperiences.title": {"$in": expand(job_titles, TITLE_VARIANTS)}}
            )

        # Min experience
        if isinstance(min_experience_years, int) and min_experience_years > 0:
            and_clauses.append(
                {
                    "$expr": {
                        "$gte": [
                            {"$toDouble": {"$ifNull": [{"$first": "$jobExperiences.duration"}, "0"]}},
                            min_experience_years,
                        ]
                    }
                }
            )

        # Combine AND clauses
        if and_clauses:
            mongo_q["$and"] = and_clauses

        # DB query
        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            candidates = list(coll.find(mongo_q, {"_id": 0, "embedding": 0}).limit(top_k))

        # LLM re-ranking
        best_ids = score_resumes(query, candidates)
        best_resumes = [r for r in candidates if r["resumeId"] in best_ids]

        return {
            "message": f"{len(best_resumes)} resumes after scoring.",
            "results_count": len(best_resumes),
            "results": best_resumes,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except PyMongoError as err:
        return {"error": f"DB error: {str(err)}"}
    except Exception as exc:
        return {"error": str(exc)}

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send a plain-text email."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, to
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
    """Return how many jobIds each resumeId is matched to."""
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
    """Look up a resumeId by candidate name."""
    try:
        if "resume_ids" not in st.session_state:
            return {"error": "No resume IDs are stored in the current session."}

        name_norm = " ".join(name.lower().split())

        # Check session cache
        for k, v in st.session_state.resume_ids.items():
            if name_norm == k.lower() or name_norm in k.lower():
                return {"found": True, "name": k, "resumeId": v}

        # DB lookup
        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            query = {
                "$or": [
                    {"name": {"$regex": name, "$options": "i"}},
                    {"fullName": {"$regex": name, "$options": "i"}},
                ]
            }
            doc = coll.find_one(query, {"_id": 0, "resumeId": 1, "name": 1, "fullName": 1})
            if doc and doc.get("resumeId"):
                display_name = doc.get("name") or doc.get("fullName") or name
                return {"found": True, "name": display_name, "resumeId": doc["resumeId"]}
        return {"found": False, "message": f"No resumeId found for '{name}'"}
    except Exception as e:
        return {"error": str(e)}

# ── PARSE / PROCESS RESPONSE ──────────────────────────────────────────
def extract_resume_ids_from_response(response_text: str) -> Dict[str, str]:
    meta_match = re.search(r"<!--RESUME_META:(.*?)-->", response_text)
    if meta_match:
        try:
            meta_data = json.loads(meta_match.group(1))
            return {item.get("name"): item.get("resumeId") for item in meta_data if item.get("resumeId")}
        except Exception:
            return {}
    return {}

def process_response(text: str) -> Dict[str, Any]:
    """
    Detects whether the assistant message is a resume list and returns
    a structured form the UI can use.
    """
    if (
        "Here are some" in text
        and ("Experience:" in text or "experience:" in text)
        and ("Skills:" in text or "skills:" in text)
    ):
        intro_match = re.search(r"^(.*?)\n\n([A-Z][a-z]+.*?)\n\nEmail:", text, re.DOTALL)
        intro_text = intro_match.group(1).strip() if intro_match else ""

        resume_pattern = (
            r"([A-Z][a-z]+ (?:[A-Z][a-z]+ )?(?:[A-Z][a-z]+)?)\s*\n\s*Email:\s*([^\n]+)\s*\n"
            r"Contact No:\s*([^\n]+)\s*\nLocation:\s*([^\n]+)\s*\nExperience:\s*([^\n]+)\s*\n"
            r"Skills:\s*([^\n]+)"
        )
        matches = re.findall(resume_pattern, text, re.MULTILINE | re.IGNORECASE)
        if not matches:
            resume_pattern = (
                r"\d+\.\s+\*\*([^*]+)\*\*\s*\n\s*-\s+\*\*Email:\*\*\s+([^\n]+)\s*\n"
                r"\s*-\s+\*\*Contact No:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Location:\*\*\s+([^\n]+)\s*\n"
                r"\s*-\s+\*\*Experience:\*\*\s+([^\n]+)\s*\n\s*-\s+\*\*Skills:\*\*\s+([^\n]+)"
            )
            matches = re.findall(resume_pattern, text, re.MULTILINE)

        conclusion_match = re.search(r"(These candidates.*?)\s*$", text, re.DOTALL)
        conclusion_text = conclusion_match.group(1).strip() if conclusion_match else ""

        resumes = []
        for match in matches:
            name, email, contact, location, experience, skills = match
            resumes.append(
                {
                    "name": name.strip(),
                    "email": email.strip(),
                    "contactNo": contact.strip(),
                    "location": location.strip(),
                    "experience": [e.strip() for e in experience.split(",")],
                    "skills": [s.strip() for s in skills.split(",")],
                }
            )

        return {
            "is_resume_response": True,
            "intro_text": intro_text,
            "resumes": resumes,
            "conclusion_text": conclusion_text,
            "full_text": text,
        }
    return {"is_resume_response": False, "full_text": text}

# ── HELPER: attach missing resumeIds ───────────────────────────────────
def attach_hidden_resume_ids(resume_list: List[Dict[str, Any]]) -> None:
    if not resume_list:
        return
    with get_mongo_client() as client:
        coll = client[DB_NAME][COLL_NAME]
        for res in resume_list:
            if res.get("resumeId"):
                continue
            doc = coll.find_one(
                {"email": res.get("email"), "contactNo": res.get("contactNo")},
                {"_id": 0, "resumeId": 1},
            )
            if doc and doc.get("resumeId"):
                res["resumeId"] = doc["resumeId"]

# ── DISPLAY GRID ───────────────────────────────────────────────────────
def display_resume_grid(resumes: List[Dict[str, Any]], container=None) -> None:
    target = container if container else st
    if not resumes:
        target.warning("No resumes found matching the criteria.")
        return

    target.markdown(
        """
    <style>
    .resume-card{border:1px solid #e1e4e8;border-radius:10px;padding:16px;margin-bottom:15px;background-color:#fff;box-shadow:0 3px 8px rgba(0,0,0,0.05);height:100%;transition:transform .2s,box-shadow .2s;}
    .resume-card:hover{transform:translateY(-3px);box-shadow:0 5px 15px rgba(0,0,0,0.1);}
    .resume-name{font-weight:700;font-size:18px;margin-bottom:8px;color:#24292e;}
    .resume-location{color:#586069;font-size:14px;margin-bottom:10px;}
    .resume-contact{margin-bottom:8px;font-size:14px;color:#444d56;}
    .resume-section-title{font-weight:600;margin-top:12px;margin-bottom:6px;font-size:15px;color:#24292e;}
    .resume-experience{font-size:14px;color:#444d56;margin-bottom:4px;}
    .skill-tag{display:inline-block;background-color:#f1f8ff;color:#0366d6;border-radius:12px;padding:3px 10px;margin:3px;font-size:12px;font-weight:500;}
    .job-matches{margin-top:8px;padding:4px 10px;background-color:#E3F2FD;border-radius:4px;display:inline-block;font-size:14px;color:#0D47A1;}
    .resume-id{font-size:10px;color:#6a737d;margin-top:8px;word-break:break-all;}
    </style>
    """,
        unsafe_allow_html=True,
    )

    rows = (len(resumes) + 2) // 3
    for r in range(rows):
        cols = target.columns(3)
        for c in range(3):
            i = r * 3 + c
            if i >= len(resumes):
                continue
            resume = resumes[i]
            name = resume.get("name", "Unknown")
            email = resume.get("email", "")
            phone = resume.get("contactNo", "")
            location = resume.get("location", "")
            resume_id = resume.get("resumeId", "")
            experience = resume.get("experience", [])
            skills = resume.get("skills", [])
            job_matches = resume.get("jobsMatched")

            with cols[c]:
                html = f'<div class="resume-card"{" data-resume-id="+resume_id if resume_id else ""}>'
                html += f'<div class="resume-name">{name}</div>'
                html += f'<div class="resume-location">📍 {location}</div>'
                html += f'<div class="resume-contact">📧 {email}</div>'
                html += f'<div class="resume-contact">📱 {phone}</div>'

                if job_matches is not None:
                    html += f'<div class="job-matches">🔗 Matched to {job_matches} jobs</div>'

                if experience:
                    html += '<div class="resume-section-title">Experience</div>'
                    for exp in experience[:3]:
                        html += f'<div class="resume-experience">• {exp}</div>'

                if skills:
                    html += '<div class="resume-section-title">Skills</div><div>'
                    for skill in skills[:7]:
                        html += f'<span class="skill-tag">{skill}</span>'
                    html += '</div>'

                if "debug_mode" in globals() and debug_mode and resume_id:
                    html += f'<div class="resume-id">ID: {resume_id}</div>'

                html += "</div>"
                st.markdown(html, unsafe_allow_html=True)

# ── AGENT & MEMORY ────────────────────────────────────────────────────
llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0)

agent_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
You are a helpful HR assistant named ZappBot.

# Resume Formatting
When displaying resume results, always format them consistently as follows:

First, provide a brief introduction line like:
"Here are some developers in [location] with [criteria]:"

Then, list each candidate in this exact format:

[Full Name]

Email: [email]
Contact No: [phone]
Location: [location]
Experience: [experience1], [experience2], [experience3]
Skills: [skill1], [skill2], [skill3], [skill4]

Maintain this precise format with consistent spacing and no bullet points or numbering, as it allows our UI to extract and display the resumes in a grid layout.

After listing all candidates, include a brief concluding sentence like:
"These candidates have diverse experiences and skills that may suit your needs."

- **Never join multiple candidates or items on one line, and never use commas or paragraphs to join candidates.**
- **Always keep each candidate in the exact block and field order above, with a blank line between candidates.**

# ResumeIDs and Tools
When a user asks about a specific candidate by name, use the `get_resume_id_by_name` tool to look up their resumeId.  
Then use this resumeId with the `get_job_match_counts` tool to find how many jobs they are matched to.  
If the user asks to email results, call the `send_email` tool.
            """,
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history", return_messages=True
    )
if "resume_ids" not in st.session_state:
    st.session_state.resume_ids = {}
if "processed_responses" not in st.session_state:
    st.session_state.processed_responses = {}
if "job_match_data" not in st.session_state:
    st.session_state.job_match_data = {}

tools = [query_db, send_email, get_job_match_counts, get_resume_id_by_name]
if "agent_executor" not in st.session_state:
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=agent, tools=tools, memory=st.session_state.memory, verbose=True
    )
    st.session_state.agent_upgraded = True
elif not st.session_state.get("agent_upgraded", False):
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=agent, tools=tools, memory=st.session_state.memory, verbose=True
    )
    st.session_state.agent_upgraded = True

# ── STREAMLIT UI ───────────────────────────────────────────────────────
st.set_page_config(page_title="ZappBot", layout="wide")

st.markdown(
    """
<style>
.stApp{max-width:1200px;margin:0 auto;}
.header-container{display:flex;align-items:center;margin-bottom:20px;}
.header-emoji{font-size:36px;margin-right:10px;}
.header-text{font-size:24px;font-weight:600;}
.resume-section{margin-top:20px;padding:15px;border-radius:8px;background-color:#f8f9fa;border-left:4px solid #0366d6;}
.resume-query{font-weight:600;margin-bottom:10px;color:#0366d6;}
.st-expander{border:none !important;box-shadow:none !important;}
.tool-section{background-color:#f8f9fa;padding:15px;border-radius:8px;margin-bottom:20px;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="header-container"><div class="header-emoji">⚡</div><div class="header-text">ZappBot</div></div>',
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    st.header("Settings")
    debug_mode = st.checkbox("Debug Mode", value=False)

    st.subheader("Email Settings")
    default_recipient = st.text_input(
        "Default Email Recipient",
        placeholder="recipient@example.com",
        help="Default email to use when sending resume results",
    )

    st.subheader("Job Matching")
    st.markdown(
        """
Ask:
How many jobs is [Candidate Name] matched to?
"""
    )

    if st.button("Clear Chat History"):
        st.session_state.memory.clear()
        st.session_state.processed_responses = {}
        st.session_state.job_match_data = {}
        st.session_state.resume_ids = {}
        st.rerun()

chat_container = st.container()

# ── USER INPUT ────────────────────────────────────────────────────────
user_input = st.chat_input("Ask me to find resumes...")
if user_input:
    with st.spinner("Thinking..."):
        try:
            response = st.session_state.agent_executor.invoke({"input": user_input})
            response_text = response["output"]

            resume_ids = extract_resume_ids_from_response(response_text)
            if resume_ids:
                st.session_state.resume_ids.update(resume_ids)

            processed = process_response(response_text)

            if "jobsMatched" in response_text:
                try:
                    m = re.search(r'"results":\s*(\[.*?\])', response_text)
                    if m:
                        data = json.loads(m.group(1))
                        for item in data:
                            rid = item.get("resumeId")
                            if rid:
                                st.session_state.job_match_data[rid] = item.get("jobsMatched", 0)
                except Exception:
                    pass

            msg_key = f"user_{datetime.now().isoformat()}"
            st.session_state.processed_responses[msg_key] = processed
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
            if debug_mode:
                st.exception(e)

# ── CHAT HISTORY + GRIDS ──────────────────────────────────────────────
with chat_container:
    resume_responses = []
    for i, msg in enumerate(st.session_state.memory.chat_memory.messages):
        if msg.type == "human":
            st.chat_message("user").write(msg.content)
            if i + 1 < len(st.session_state.memory.chat_memory.messages):
                next_msg = st.session_state.memory.chat_memory.messages[i + 1]
                if next_msg.type == "ai":
                    ai_key = f"ai_{i+1}"
                    if ai_key not in st.session_state.processed_responses:
                        st.session_state.processed_responses[ai_key] = process_response(
                            next_msg.content
                        )
                    processed_ai = st.session_state.processed_responses[ai_key]
                    if processed_ai["is_resume_response"]:
                        resume_responses.append(
                            {"query": msg.content, "processed": processed_ai, "index": i + 1}
                        )
        else:
            ai_key = f"ai_{i}"
            if ai_key not in st.session_state.processed_responses:
                st.session_state.processed_responses[ai_key] = process_response(msg.content)
            processed = st.session_state.processed_responses[ai_key]

            ai_message = st.chat_message("assistant")
            if processed["is_resume_response"]:
                extracted = extract_resume_ids_from_response(processed["full_text"])
                if extracted:
                    st.session_state.resume_ids.update(extracted)

                hidden_meta = json.dumps(
                    [
                        {"name": r.get("name"), "resumeId": r.get("resumeId", "")}
                        for r in processed["resumes"]
                    ]
                )
                ai_message.write(processed["intro_text"])
                if processed.get("conclusion_text"):
                    ai_message.write(processed["conclusion_text"])
            else:
                ai_message.write(processed["full_text"])

    if resume_responses:
        st.markdown("---")
        st.subheader("Resume Search Results")
        for i, resp in enumerate(resume_responses):
            with st.expander(
                f"Search {i+1}: {resp['query']}", expanded=(i == len(resume_responses) - 1)
            ):
                st.markdown(
                    f"<div class='resume-query'>{resp['processed']['intro_text']}</div>",
                    unsafe_allow_html=True,
                )

                attach_hidden_resume_ids(resp["processed"]["resumes"])

                for r in resp["processed"]["resumes"]:
                    if r.get("resumeId") and r.get("name"):
                        st.session_state.resume_ids[r["name"]] = r["resumeId"]

                if st.session_state.job_match_data:
                    for r in resp["processed"]["resumes"]:
                        rid = r.get("resumeId")
                        if rid and rid in st.session_state.job_match_data:
                            r["jobsMatched"] = st.session_state.job_match_data[rid]

                display_resume_grid(resp["processed"]["resumes"])

                cols = st.columns([2, 1, 1])
                with cols[1]:
                    if resp["processed"]["resumes"]:
                        if st.button(f"📧 Email Results", key=f"email_btn_{i}"):
                            if not default_recipient:
                                st.error("Please set a default email recipient in the sidebar.")
                            else:
                                body = reformat_email_body(
                                    resp["processed"]["resumes"],
                                    intro=resp["processed"]["intro_text"],
                                    conclusion=resp["processed"].get("conclusion_text", ""),
                                )
                                res = send_email(
                                    to=default_recipient,
                                    subject=f"ZappBot Results: {resp['query']}",
                                    body=body,
                                )
                                if res.startswith("Email sent"):
                                    st.success(f"Email sent to {default_recipient}")
                                else:
                                    st.error(res)

                with cols[2]:
                    if resp["processed"]["resumes"]:
                        if st.button("🔍 Match Jobs", key=f"job_btn_{i}"):
                            ids = [r.get("resumeId") for r in resp["processed"]["resumes"] if r.get("resumeId")]
                            if ids:
                                result = get_job_match_counts(ids)
                                if "results" in result:
                                    for item in result["results"]:
                                        rid = item.get("resumeId")
                                        if rid:
                                            st.session_state.job_match_data[rid] = item.get("jobsMatched", 0)
                                    st.success("Job match data updated")
                                    st.rerun()
                                else:
                                    st.error("Failed to get job match data")

                if resp["processed"].get("conclusion_text"):
                    st.write(resp["processed"]["conclusion_text"])

    if debug_mode:
        with st.expander("Debug Information"):
            st.subheader("Memory")
            st.json({i: m.content for i, m in enumerate(st.session_state.memory.chat_memory.messages)})
            st.subheader("Resume IDs")
            st.json(st.session_state.resume_ids)
            st.subheader("Processed Responses (truncated)")
            for k, v in st.session_state.processed_responses.items():
                if "full_text" in v:
                    short = {kk: vv for kk, vv in v.items() if kk != "full_text"}
                    short["full_text_length"] = len(v["full_text"])
                    st.json({k: short})
                else:
                    st.json({k: v})
            st.subheader("Job Match Data")
            st.json(st.session_state.job_match_data)
