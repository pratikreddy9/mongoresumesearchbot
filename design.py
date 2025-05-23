import streamlit as st
from typing import List, Dict, Any

def display_resume_grid(resumes, container=None):
    """
    Display resumes in a 3-column grid layout with clean glassmorphism cards.
    
    Args:
        resumes: List of resume dictionaries to display
        container: Optional Streamlit container to render into (defaults to st)
    """
    target = container if container else st
    
    if not resumes:
        target.warning("🔍 No resumes found matching the criteria.")
        return
    
    # Clean Professional CSS
    target.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    .resume-card {
        background: rgba(255,255,255,0.08);
        backdrop-filter: blur(15px);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid rgba(255,255,255,0.15);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
        height: auto;
        min-height: 350px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.12);
        font-family: 'Inter', sans-serif;
        margin-bottom: 20px;
    }
    
    .resume-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(0,0,0,0.2);
        border: 1px solid rgba(255,255,255,0.25);
        background: rgba(255,255,255,0.12);
    }
    
    .resume-name {
        font-weight: 700;
        font-size: 20px;
        margin-bottom: 10px;
        color: #FFFFFF;
        text-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    
    .resume-location {
        color: #B0BEC5;
        font-size: 13px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        font-weight: 500;
    }
    
    .resume-contact {
        margin-bottom: 6px;
        font-size: 12px;
        color: #CFD8DC;
        display: flex;
        align-items: center;
        font-weight: 400;
        opacity: 0.9;
    }
    
    .resume-section-title {
        font-weight: 600;
        margin-top: 16px;
        margin-bottom: 10px;
        font-size: 14px;
        color: #FFFFFF;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        opacity: 0.9;
    }
    
    .resume-experience {
        font-size: 12px;
        color: #E0E0E0;
        margin-bottom: 4px;
        padding-left: 8px;
        position: relative;
        font-weight: 400;
        line-height: 1.3;
    }
    
    .resume-experience::before {
        content: '•';
        position: absolute;
        left: 0;
        color: #64B5F6;
        font-weight: bold;
    }
    
    /* Skills - ALL Blue theme */
    .skill-tag {
        display: inline-block;
        background: rgba(33, 150, 243, 0.2);
        color: #64B5F6;
        border-radius: 12px;
        padding: 4px 10px;
        margin: 3px 4px 3px 0;
        font-size: 10px;
        font-weight: 500;
        border: 1px solid rgba(33, 150, 243, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.2s ease;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    
    .skill-tag:hover {
        background: rgba(33, 150, 243, 0.3);
        border: 1px solid rgba(33, 150, 243, 0.5);
    }
    
    /* ONLY Matched Skills - Orange theme */
    .skill-tag.highlight {
        background: rgba(255, 152, 0, 0.2);
        color: #FFB74D;
        border: 1px solid rgba(255, 152, 0, 0.4);
    }
    
    .skill-tag.highlight:hover {
        background: rgba(255, 152, 0, 0.3);
        border: 1px solid rgba(255, 152, 0, 0.6);
    }
    
    /* Keywords - ALL Green theme */
    .keyword-tag {
        display: inline-block;
        background: rgba(76, 175, 80, 0.2);
        color: #81C784;
        border-radius: 12px;
        padding: 4px 10px;
        margin: 3px 4px 3px 0;
        font-size: 10px;
        font-weight: 500;
        border: 1px solid rgba(76, 175, 80, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.2s ease;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    
    .keyword-tag:hover {
        background: rgba(76, 175, 80, 0.3);
        border: 1px solid rgba(76, 175, 80, 0.5);
    }
    
    /* ONLY Matched Keywords - Purple theme */
    .keyword-tag.highlight {
        background: rgba(156, 39, 176, 0.2);
        color: #BA68C8;
        border: 1px solid rgba(156, 39, 176, 0.4);
    }
    
    .keyword-tag.highlight:hover {
        background: rgba(156, 39, 176, 0.3);
        border: 1px solid rgba(156, 39, 176, 0.6);
    }
    
    .job-matches {
        margin-top: 12px;
        padding: 8px 12px;
        background: rgba(69, 183, 209, 0.2);
        border-radius: 20px;
        display: inline-flex;
        align-items: center;
        font-size: 11px;
        color: #4FC3F7;
        font-weight: 600;
        border: 1px solid rgba(69, 183, 209, 0.3);
        backdrop-filter: blur(10px);
    }
    
    .job-matches::before {
        content: '🎯';
        margin-right: 6px;
        font-size: 12px;
    }
    
    .stats-badge {
        position: absolute;
        bottom: 15px;
        right: 15px;
        background: rgba(0,0,0,0.6);
        color: #E0E0E0;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 9px;
        font-weight: 600;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    
    .resume-id {
        font-size: 8px;
        color: rgba(255,255,255,0.4);
        margin-top: 12px;
        word-break: break-all;
        font-family: 'Courier New', monospace;
        background: rgba(0,0,0,0.3);
        padding: 3px 6px;
        border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .more-items {
        font-size: 9px;
        color: rgba(255,255,255,0.5);
        font-style: italic;
        margin-left: 6px;
        background: rgba(255,255,255,0.1);
        padding: 3px 8px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
    }
    
    /* Mobile responsiveness */
    @media (max-width: 768px) {
        .resume-card {
            padding: 16px;
            min-height: 320px;
        }
        
        .resume-name {
            font-size: 18px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create a 3-column grid
    num_resumes = len(resumes)
    rows = (num_resumes + 2) // 3  # Ceiling division for number of rows
    
    # Highlighted terms for matching
    highlight_terms = ['python', 'sql', 'mysql', 'postgresql', 'py', 'java', 'javascript', 'react', 'node']
    
    for row in range(rows):
        cols = target.columns(3)
        for col in range(3):
            idx = row * 3 + col
            if idx < num_resumes:
                resume = resumes[idx]
                
                # Extract resume data
                name = resume.get("name", "Unknown")
                email = resume.get("email", "")
                phone = resume.get("contactNo", "")
                location = resume.get("location", "")
                resume_id = resume.get("resumeId", "")
                
                # Get experience and skills
                experience = resume.get("experience", [])
                skills = resume.get("skills", [])
                keywords = resume.get("keywords", [])
                
                # Get job matches if available
                job_matches = resume.get("jobsMatched")
                
                with cols[col]:
                    # Calculate stats for badge
                    total_skills = len(skills) + len(keywords)
                    
                    html = f"""
                    <div class="resume-card" data-resume-id="{resume_id}">
                        <div class="resume-name">{name}</div>
                        <div class="resume-location">📍 {location}</div>
                        <div class="resume-contact">📧 {email}</div>
                        <div class="resume-contact">📱 {phone}</div>
                    """
                    
                    # Add job matches if available
                    if job_matches is not None:
                        html += f'<div class="job-matches">Matched to {job_matches} jobs</div>'
                    
                    # Add experience section
                    if experience:
                        html += f'<div class="resume-section-title">💼 Experience</div>'
                        for exp in experience[:3]:  # Limit to 3 experiences
                            html += f'<div class="resume-experience">{exp}</div>'
                    
                    # Add skills section - Show ALL skills with highlighting
                    if skills:
                        html += f'<div class="resume-section-title">🚀 Skills</div><div>'
                        
                        # Show ALL skills with highlighting
                        for skill in skills:
                            skill_name = skill if isinstance(skill, str) else skill.get('skillName', '')
                            # Check if this skill should be highlighted
                            is_highlight = any(term.lower() in skill_name.lower() for term in highlight_terms)
                            highlight_class = ' highlight' if is_highlight else ''
                            html += f'<span class="skill-tag{highlight_class}">{skill_name}</span>'
                        
                        html += '</div>'
                    
                    # Add keywords section - Show ALL keywords with highlighting
                    if keywords:
                        html += f'<div class="resume-section-title">🏷️ Keywords</div><div>'
                        
                        # Show ALL keywords with highlighting
                        for keyword in keywords:
                            # Check if this keyword should be highlighted
                            is_highlight = any(term.lower() in keyword.lower() for term in highlight_terms)
                            highlight_class = ' highlight' if is_highlight else ''
                            html += f'<span class="keyword-tag{highlight_class}">{keyword}</span>'
                        
                        html += '</div>'
                    
                    # Add stats badge at bottom right
                    html += f'<div class="stats-badge">{total_skills} Skills</div>'
                    
                    # Show resume ID in debug mode
                    debug_mode = getattr(st.session_state, 'debug_mode', False)
                    if debug_mode and resume_id:
                        html += f'<div class="resume-id">🆔 {resume_id}</div>'
                    
                    html += '</div>'
                    st.markdown(html, unsafe_allow_html=True)
