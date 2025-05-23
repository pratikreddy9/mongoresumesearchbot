"""
ZappBot: Resume‑filtering chatbot with optimized display + email sender + job match counts
LangChain 0.3.25 • OpenAI 1.78.1 • Streamlit 1.34+
"""

import os, json, re
from datetime import datetime

import streamlit as st
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory

# Import modular components
from prompts import agent_prompt
from design import display_resume_grid
from variants import expand
from utils import (
    get_mongo_client, 
    extract_resume_ids_from_response, 
    process_response, 
    attach_hidden_resume_ids
)
from tools import query_db, send_email, get_job_match_counts, get_resume_id_by_name

# ── CONFIG ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
MODEL_NAME = "gpt-4o"
DB_NAME = "resumes_database"
COLL_NAME = "resumes"

# ── AGENT + MEMORY ─────────────────────────────────────────────────────
llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0)

# Initialize session state variables
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

# Initialize or upgrade the agent
tools = [query_db, send_email, get_job_match_counts, get_resume_id_by_name]
if "agent_executor" not in st.session_state:
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools,
        memory=st.session_state.memory, 
        verbose=True
    )
    st.session_state.agent_upgraded = True
elif not st.session_state.get("agent_upgraded", False):
    upgraded_agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=upgraded_agent,
        tools=tools,
        memory=st.session_state.memory,
        verbose=True,
    )
    st.session_state.agent_upgraded = True

# ── STREAMLIT UI ───────────────────────────────────────────────────────
st.set_page_config(page_title="⚡ ZappBot", layout="wide", initial_sidebar_state="expanded")

# Clean Enhanced CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    /* Clean dark theme */
    .stApp {
        background: #1a1a1a;
        font-family: 'Inter', sans-serif;
        max-width: none !important;
        color: white;
    }
    
    /* Enhanced header with gold gradient */
    .header-container {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 30px;
        padding: 20px;
        background: rgba(255,255,255,0.05);
        border-radius: 15px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .header-emoji {
        font-size: 42px;
        margin-right: 15px;
        filter: drop-shadow(0 0 10px rgba(255,215,0,0.3));
    }
    
    .header-text {
        font-size: 36px;
        font-weight: 800;
        background: linear-gradient(135deg, #FFD700, #FFA500);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 20px rgba(255,215,0,0.2);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: rgba(0,0,0,0.6);
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(255,255,255,0.1);
    }
    
    /* Chat messages - Clean white background */
    .stChatMessage {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        margin: 8px 0 !important;
    }
    
    .stChatMessage .stMarkdown {
        color: white !important;
    }
    
    /* Enhanced buttons */
    .stButton > button {
        background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 20px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 6px 20px rgba(74, 144, 226, 0.3) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(74, 144, 226, 0.4) !important;
        background: linear-gradient(135deg, #357abd 0%, #2968a3 100%) !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: rgba(255,255,255,0.08) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 12px !important;
        color: white !important;
        padding: 12px 16px !important;
    }
    
    .stTextInput > div > div > input::placeholder {
        color: rgba(255,255,255,0.6) !important;
    }
    
    /* Chat input */
    .stChatInputContainer {
        background: rgba(0,0,0,0.4) !important;
        backdrop-filter: blur(20px) !important;
        border-radius: 20px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    
    /* Success/Error messages */
    .stSuccess {
        background: rgba(76, 175, 80, 0.15) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(76, 175, 80, 0.3) !important;
        border-radius: 12px !important;
        color: #81C784 !important;
    }
    
    .stError {
        background: rgba(244, 67, 54, 0.15) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(244, 67, 54, 0.3) !important;
        border-radius: 12px !important;
        color: #EF5350 !important;
    }
    
    /* Checkbox and selectbox */
    .stCheckbox {
        color: white !important;
    }
    
    .stSelectbox > div > div {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 12px !important;
        color: white !important;
    }
    
    /* Sidebar text */
    .css-1d391kg .stMarkdown {
        color: white !important;
    }
    
    /* Main content text */
    .main .stMarkdown {
        color: white !important;
    }
    
    /* Floating stats */
    .floating-stats {
        position: fixed;
        top: 20px;
        right: 20px;
        background: rgba(0,0,0,0.8);
        backdrop-filter: blur(20px);
        border-radius: 12px;
        padding: 12px 16px;
        color: white;
        font-weight: 600;
        border: 1px solid rgba(255,255,255,0.2);
        z-index: 1000;
        font-size: 14px;
    }
    
    /* Results header */
    .resume-results-header {
        text-align: center;
        color: white;
        font-size: 24px;
        font-weight: 700;
        margin: 30px 0 20px 0;
        text-shadow: 0 0 15px rgba(255,255,255,0.2);
    }
</style>
""", unsafe_allow_html=True)

# Floating Stats Counter
total_resumes = len(st.session_state.resume_ids)
st.markdown(f"""
<div class="floating-stats">
    📊 {total_resumes} Resumes Loaded
</div>
""", unsafe_allow_html=True)

# Clean Header
st.markdown('''
<div class="header-container">
    <div class="header-emoji">⚡</div>
    <div class="header-text">ZappBot</div>
</div>
''', unsafe_allow_html=True)

# Enhanced Sidebar
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    debug_mode = st.checkbox("🐛 Debug Mode", value=False)
    
    st.markdown("### 📧 Email Settings")
    default_recipient = st.text_input("Default Email Recipient", 
                                     placeholder="recipient@example.com",
                                     help="Default email to use when sending resume results")
    
    st.markdown("### 🎯 Job Matching")
    st.markdown("""
    💡 **Quick Tip**: Ask about specific candidates:
    ```
    How many jobs is [Candidate Name] matched to?
    ```
    """)
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.memory.clear()
        st.session_state.processed_responses = {}
        st.session_state.job_match_data = {}
        st.session_state.resume_ids = {}
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 📈 Session Stats")
    st.metric("💼 Resumes Found", len(st.session_state.resume_ids))
    st.metric("🎯 Job Matches", len(st.session_state.job_match_data))
    st.metric("💬 Conversations", len(st.session_state.memory.chat_memory.messages) // 2)

# Main chat container
chat_container = st.container()

# Handle user input
user_input = st.chat_input("🔍 Ask me to find the perfect resumes...")
if user_input:
    with st.spinner("🧠 AI is thinking..."):
        try:
            response = st.session_state.agent_executor.invoke({"input": user_input})
            response_text = response["output"]
            
            resume_ids = extract_resume_ids_from_response(response_text)
            if resume_ids:
                st.session_state.resume_ids.update(resume_ids)
            
            processed = process_response(response_text)
            
            if "jobsMatched" in response_text:
                try:
                    matches_pattern = r'"results":\s*(\[.*?\])'
                    matches_match = re.search(matches_pattern, response_text)
                    if matches_match:
                        match_data = json.loads(matches_match.group(1))
                        for item in match_data:
                            resume_id = item.get("resumeId")
                            if resume_id:
                                st.session_state.job_match_data[resume_id] = item.get("jobsMatched", 0)
                except:
                    pass
            
            timestamp = datetime.now().isoformat()
            message_key = f"user_{timestamp}"
            st.session_state.processed_responses[message_key] = processed
            
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            if debug_mode:
                st.exception(e)

# Display chat history
with chat_container:
    resume_responses = []
    
    for i, msg in enumerate(st.session_state.memory.chat_memory.messages):
        if msg.type == "human":
            st.chat_message("user", avatar="👤").write(msg.content)
            
            if i+1 < len(st.session_state.memory.chat_memory.messages):
                next_msg = st.session_state.memory.chat_memory.messages[i+1]
                if next_msg.type == "ai":
                    ai_msg_key = f"ai_{i+1}"
                    
                    if ai_msg_key not in st.session_state.processed_responses:
                        st.session_state.processed_responses[ai_msg_key] = process_response(next_msg.content)
                    
                    processed_ai = st.session_state.processed_responses[ai_msg_key]
                    
                    if processed_ai["is_resume_response"]:
                        resume_responses.append({
                            "query": msg.content,
                            "processed": processed_ai,
                            "index": i+1
                        })
                        
        else:
            msg_key = f"ai_{i}"
            if msg_key not in st.session_state.processed_responses:
                st.session_state.processed_responses[msg_key] = process_response(msg.content)
            
            processed = st.session_state.processed_responses[msg_key]
            
            ai_message = st.chat_message("assistant", avatar="⚡")
            if processed["is_resume_response"]:
                resume_ids = extract_resume_ids_from_response(processed["full_text"])
                if resume_ids:
                    st.session_state.resume_ids.update(resume_ids)
                
                hidden_meta = json.dumps([{"name": r.get("name"), "resumeId": r.get("resumeId", "")}for r in processed["resumes"]])
                for item in json.loads(hidden_meta):
                    if item.get("name") and item.get("resumeId"):
                        st.session_state.resume_ids[item["name"]] = item["resumeId"]
                        
                ai_message.write(processed["intro_text"])
                
                if processed.get("conclusion_text"):
                    ai_message.write(processed["conclusion_text"])
            else:
                ai_message.write(processed["full_text"])
    
    # Display resume grids
    if resume_responses:
        st.markdown('<div class="resume-results-header">🎯 Resume Search Results</div>', unsafe_allow_html=True)
        
        for i, resp in enumerate(resume_responses):
            with st.expander(f"🔍 Search {i+1}: {resp['query']}", expanded=(i == len(resume_responses)-1)):
                st.markdown(f"**{resp['processed']['intro_text']}**")
                
                attach_hidden_resume_ids(resp['processed']['resumes'])
                
                for resume in resp['processed']['resumes']:
                    if resume.get("resumeId") and resume.get("name"):
                        st.session_state.resume_ids[resume["name"]] = resume["resumeId"]
                
                if st.session_state.job_match_data:
                    for resume in resp['processed']['resumes']:
                        resume_id = resume.get("resumeId")
                        if resume_id and resume_id in st.session_state.job_match_data:
                            resume["jobsMatched"] = st.session_state.job_match_data[resume_id]
                
                display_resume_grid(resp['processed']['resumes'])
                
                # Closer button layout - side by side
                cols = st.columns([2, 1, 1, 1])
                
                with cols[2]:
                    if resp['processed']['resumes']:
                        if st.button(f"📧 Email", key=f"email_btn_{i}"):
                            try:
                                from utils import reformat_email_body
                                
                                plain_text_body = reformat_email_body(
                                    llm_output=resp['processed']['resumes'],
                                    intro=resp['processed']['intro_text'],
                                    conclusion=resp['processed'].get('conclusion_text', '')
                                )
                                
                                recipient = default_recipient
                                if not recipient:
                                    st.error("❌ Please set email recipient in sidebar.")
                                else:
                                    result = send_email(
                                        to=recipient,
                                        subject=f"ZappBot Results: {resp['query']}",
                                        body=plain_text_body
                                    )
                                    st.success(f"✅ Email sent to {recipient}")
                            except Exception as e:
                                st.error(f"❌ Failed to send email: {str(e)}")
                
                with cols[3]:
                    if resp['processed']['resumes']:
                        if st.button("🎯 Jobs", key=f"job_btn_{i}"):
                            try:
                                resume_ids = []
                                for resume in resp['processed']['resumes']:
                                    resume_id = resume.get("resumeId")
                                    if resume_id:
                                        resume_ids.append(resume_id)
                                
                                if resume_ids:
                                    response = st.session_state.agent_executor.invoke({
                                        "input": f"Get job match counts for these resume IDs: {resume_ids}"
                                    })
                                    
                                    response_text = response["output"]
                                    if "jobsMatched" in response_text:
                                        try:
                                            matches_pattern = r"'results':\s*(\[.*?\])"
                                            matches_match = re.search(matches_pattern, response_text, re.DOTALL)
                                            if matches_match:
                                                results_str = matches_match.group(1)
                                                results_str = results_str.replace("'", '"')
                                                match_data = json.loads(results_str)
                                                
                                                for item in match_data:
                                                    resume_id = item.get("resumeId")
                                                    if resume_id:
                                                        st.session_state.job_match_data[resume_id] = item.get("jobsMatched", 0)
                                                
                                                st.success(f"🎯 Updated {len(match_data)} job matches")
                                                st.rerun()
                                            else:
                                                st.error("❌ Could not parse job match data")
                                        except Exception as parse_error:
                                            st.error(f"❌ Parse error: {str(parse_error)}")
                                    else:
                                        st.error("❌ No job match data found")
                                else:
                                    st.warning("⚠️ No resume IDs found")
                            except Exception as e:
                                st.error(f"❌ Failed to get job matches: {str(e)}")
                
                if resp['processed'].get('conclusion_text'):
                    st.write(resp['processed']['conclusion_text'])
    
    # Debug info
    if debug_mode:
        with st.expander("🐛 Debug Information"):
            st.subheader("💾 Memory Contents")
            st.json({i: msg.content for i, msg in enumerate(st.session_state.memory.chat_memory.messages)})
            
            st.subheader("🆔 Stored Resume IDs")
            st.json(st.session_state.resume_ids)
            
            st.subheader("🎯 Job Match Data")
            st.json(st.session_state.job_match_data)
    
    if debug_mode and "mongo_queries" in st.session_state and st.session_state.mongo_queries:
        with st.expander("🗄️ Recent MongoDB Queries"):
            for i, q in enumerate(st.session_state.mongo_queries):
                st.markdown(f"**Query {i+1} - {q['timestamp']}**")
                st.code(q["query"], language="json")
                st.write("Parameters:")
                st.json(q["parameters"])
                if i < len(st.session_state.mongo_queries) - 1:
                    st.markdown("---")
