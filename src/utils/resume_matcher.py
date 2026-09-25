import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from pypdf import PdfReader
from src.utils.logger import logger

COMMON_TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "golang", "rust",
    "react", "angular", "vue", "next.js", "node.js", "express", "django", "fastapi", "flask",
    "spring", "spring boot", "sql", "postgresql", "mysql", "mongodb", "redis",
    "docker", "kubernetes", "aws", "azure", "gcp", "ci/cd", "git", "linux",
    "machine learning", "deep learning", "nlp", "llm", "ai", "pandas", "numpy",
    "data science", "rest api", "graphql", "microservices", "html", "css", "tailwind"
]

class ResumeMatcher:
    def __init__(self, resume_path: Optional[Path] = None):
        self.resume_path = resume_path
        self.extracted_text = ""
        self.detected_skills: Set[str] = set()
        self.detected_title: Optional[str] = None
        if self.resume_path and Path(self.resume_path).exists():
            self._parse_resume()

    def _parse_resume(self):
        """Extracts text and key signals from PDF resume."""
        try:
            reader = PdfReader(str(self.resume_path))
            full_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
            self.extracted_text = "\n".join(full_text)
            self._detect_skills()
            self._detect_designation()
            logger.info(f"Parsed resume: detected {len(self.detected_skills)} skills")
        except Exception as e:
            logger.warning(f"Failed to parse resume at {self.resume_path}: {e}")

    def _detect_skills(self):
        lower_text = self.extracted_text.lower()
        for skill in COMMON_TECH_SKILLS:
            # Word boundary check for accurate skill detection
            pattern = r"(?:\b)" + re.escape(skill) + r"(?:\b)"
            if re.search(pattern, lower_text):
                self.detected_skills.add(skill)

    def _detect_designation(self):
        """Attempts to infer current designation from top lines of resume."""
        lines = [line.strip() for line in self.extracted_text.splitlines() if line.strip()]
        role_keywords = ["engineer", "developer", "architect", "lead", "analyst", "scientist", "manager"]
        for line in lines[:10]: # Look in first 10 non-empty lines
            lower = line.lower()
            if any(k in lower for k in role_keywords) and len(line) < 50:
                self.detected_title = line
                break

    def calculate_match_score(
        self,
        job_title: str,
        job_description: str = "",
        job_skills: Optional[List[str]] = None,
        candidate_skills: Optional[List[str]] = None,
        target_roles: Optional[List[str]] = None,
    ) -> float:
        """
        Calculates a relevance score (0.0 to 1.0) between a job posting and candidate profile.
        """
        score = 0.0
        job_title_lower = job_title.lower()
        desc_lower = job_description.lower() if job_description else ""

        # Negative checks: exclude internships or unwanted senior roles if mismatch
        unwanted_keywords = ["internship", "intern", "phd required", "director", "vp"]
        if any(unw in job_title_lower for unw in unwanted_keywords):
            return 0.1

        # 1. Title Match Score (weight: 0.5)
        if target_roles:
            for role in target_roles:
                words = role.lower().split()
                matches = sum(1 for w in words if w in job_title_lower)
                if matches > 0:
                    role_score = matches / len(words)
                    score = max(score, role_score * 0.5)

        # 2. Skill Overlap Score (weight: 0.5)
        all_candidate_skills = set(candidate_skills or []).union(self.detected_skills)
        if all_candidate_skills:
            # Check skills against job description or job skills
            skill_hits = 0
            check_text = desc_lower + " " + " ".join(job_skills or []).lower()
            if not check_text.strip():
                check_text = job_title_lower

            for s in all_candidate_skills:
                if s.lower() in check_text:
                    skill_hits += 1

            skill_score = min(skill_hits / max(len(all_candidate_skills) * 0.3, 1), 1.0) * 0.5
            score += skill_score

        return min(round(score, 2), 1.0)
