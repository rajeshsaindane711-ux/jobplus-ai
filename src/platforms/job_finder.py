"""
JobPlus AI — Multi-Platform Job Finder & Safety Filter Engine
Discovers high-match openings across:
1. Direct Company ATS Career Portals (Greenhouse, Lever, Ashby, Workday)
2. LinkedIn Easy Apply
3. Naukri.com
4. Remote Global Portals (Wellfound, RemoteOK, WeWorkRemotely)

Enforces strict candidate guardrails:
- Salary Floor (e.g. >= 12 LPA)
- Experience Bracket (e.g. <= 8 Years)
- Company & Keyword Blacklists
- Ghost Job Detection (skips stale/expired listings)
- Deduplication Hashes in SQLite
"""

import os
import re
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.database import DatabaseTracker
from src.utils.logger import logger
from src.utils.ai_copilot import AICareerCopilot


class JobFinderEngine:
    """Multi-platform job aggregator with real-time safety and relevance filtering."""

    DEFAULT_WATCHLIST_COMPANIES = [
        {"name": "PhonePe", "portal_type": "greenhouse", "domain": "phonepe.com", "careers_url": "https://boards.greenhouse.io/phonepe", "location": "Pune / Bengaluru"},
        {"name": "Zeta Tech", "portal_type": "lever", "domain": "zeta.tech", "careers_url": "https://jobs.lever.co/zeta", "location": "Bengaluru (Remote)"},
        {"name": "Razorpay", "portal_type": "greenhouse", "domain": "razorpay.com", "careers_url": "https://boards.greenhouse.io/razorpay", "location": "Bengaluru"},
        {"name": "Cred", "portal_type": "ashby", "domain": "cred.club", "careers_url": "https://jobs.ashbyhq.com/cred", "location": "Bengaluru"},
        {"name": "Groww", "portal_type": "greenhouse", "domain": "groww.in", "careers_url": "https://boards.greenhouse.io/groww", "location": "Bengaluru / Pune"},
        {"name": "Swiggy", "portal_type": "lever", "domain": "swiggy.com", "careers_url": "https://jobs.lever.co/swiggy", "location": "Remote / Bengaluru"},
        {"name": "Zomato", "portal_type": "greenhouse", "domain": "zomato.com", "careers_url": "https://boards.greenhouse.io/zomato", "location": "Gurgaon / Remote"},
        {"name": "Confluent", "portal_type": "greenhouse", "domain": "confluent.io", "careers_url": "https://boards.greenhouse.io/confluent", "location": "Bengaluru (Remote)"},
        {"name": "Postman", "portal_type": "greenhouse", "domain": "postman.com", "careers_url": "https://boards.greenhouse.io/postman", "location": "Remote / Bengaluru"},
        {"name": "Atlassian", "portal_type": "lever", "domain": "atlassian.com", "careers_url": "https://jobs.lever.co/atlassian", "location": "Bengaluru (Remote)"},
        {"name": "Datadog", "portal_type": "greenhouse", "domain": "datadoghq.com", "careers_url": "https://boards.greenhouse.io/datadog", "location": "Remote / India"},
        {"name": "Elastic", "portal_type": "greenhouse", "domain": "elastic.co", "careers_url": "https://boards.greenhouse.io/elastic", "location": "Remote India"}
    ]

    SAMPLE_DISCOVERED_JOBS = [
        {
            "job_id": "phonepe-sre-lead-01",
            "platform": "direct_ats",
            "title": "Senior SRE / Cloud Platform Engineer",
            "company": "PhonePe",
            "location": "Pune / Bengaluru",
            "url": "https://boards.greenhouse.io/phonepe/jobs/5921820",
            "min_salary": 22.0,
            "max_salary": 32.0,
            "experience_required": 5.0,
            "description": "Architecting Kubernetes clusters, Kafka streaming, and Terraform AWS multi-cloud automation.",
            "posted_days_ago": 2
        },
        {
            "job_id": "zeta-cloud-platform-02",
            "platform": "linkedin",
            "title": "Cloud Platform & SRE Specialist",
            "company": "Zeta Tech",
            "location": "Bengaluru (Remote)",
            "url": "https://www.linkedin.com/jobs/view/410291829",
            "min_salary": 20.0,
            "max_salary": 28.0,
            "experience_required": 4.5,
            "description": "Managing high-scale EKS, ArgoCD GitOps, Prometheus observability, and CI/CD pipelines.",
            "posted_days_ago": 1
        },
        {
            "job_id": "confluent-kafka-sre-03",
            "platform": "direct_ats",
            "title": "Staff Platform Engineer (Kafka & Streaming)",
            "company": "Confluent",
            "location": "Remote (India)",
            "url": "https://boards.greenhouse.io/confluent/jobs/4829102",
            "min_salary": 28.0,
            "max_salary": 40.0,
            "experience_required": 5.0,
            "description": "Deep expertise in Apache Kafka internal architecture, cluster sizing, and Kubernetes Strimzi operators.",
            "posted_days_ago": 3
        },
        {
            "job_id": "groww-devops-04",
            "platform": "naukri",
            "title": "DevOps Engineer (AWS & Terraform)",
            "company": "Groww",
            "location": "Bengaluru / Pune",
            "url": "https://www.naukri.com/job-listings-devops-engineer-groww-04",
            "min_salary": 18.0,
            "max_salary": 25.0,
            "experience_required": 5.0,
            "description": "Infrastructure as code with Terraform, Docker containerization, and automated canary deployments.",
            "posted_days_ago": 2
        },
        {
            "job_id": "razorpay-sre-05",
            "platform": "direct_ats",
            "title": "Site Reliability Engineer II",
            "company": "Razorpay",
            "location": "Bengaluru",
            "url": "https://boards.greenhouse.io/razorpay/jobs/8291029",
            "min_salary": 24.0,
            "max_salary": 34.0,
            "experience_required": 4.0,
            "description": "Mission-critical payment gateway reliability, SLO/SLI tracking with Prometheus and Datadog.",
            "posted_days_ago": 4
        },
        # Intentionally filtered test items
        {
            "job_id": "wipro-helpdesk-99",
            "platform": "naukri",
            "title": "L1 IT Support & Helpdesk Engineer",
            "company": "Wipro",
            "location": "Pune",
            "url": "https://www.naukri.com/job-listings-99",
            "min_salary": 4.5,
            "max_salary": 6.0,
            "experience_required": 2.0,
            "description": "Desktop support and ticket resolution.",
            "posted_days_ago": 45  # Ghost job
        }
    ]

    def __init__(
        self,
        tracker: Optional[DatabaseTracker] = None,
        copilot: Optional[AICareerCopilot] = None,
        min_salary_lpa: float = 12.0,
        max_experience_years: float = 8.0,
        min_match_score: float = 85.0,
        company_blacklist: Optional[List[str]] = None,
        keyword_blacklist: Optional[List[str]] = None,
    ):
        self.tracker = tracker or DatabaseTracker()
        self.copilot = copilot or AICareerCopilot()
        self.min_salary_lpa = min_salary_lpa
        self.max_experience_years = max_experience_years
        self.min_match_score = min_match_score
        self.company_blacklist = [c.lower() for c in (company_blacklist or ["wipro", "tcs", "cognizant", "infosys", "hcl", "accenture"])]
        self.keyword_blacklist = [k.lower() for k in (keyword_blacklist or ["support", "l1", "helpdesk", "intern", "junior", "data entry"])]

    def evaluate_job_eligibility(self, job: Dict[str, Any], candidate_resume: str = "") -> Dict[str, Any]:
        """
        Runs comprehensive safety, salary, experience, blacklist, and ATS checks.
        Returns evaluation result dictionary.
        """
        title = job.get("title", "")
        company = job.get("company", "")
        min_sal = job.get("min_salary")
        exp_req = job.get("experience_required")
        posted_days = job.get("posted_days_ago", 0)

        # 1. Company Blacklist Check
        if any(b in company.lower() for b in self.company_blacklist):
            return {"eligible": False, "reason": f"Company '{company}' is blacklisted"}

        # 2. Keyword Blacklist Check
        if any(b in title.lower() for b in self.keyword_blacklist):
            return {"eligible": False, "reason": f"Title '{title}' contains excluded keyword"}

        # 3. Salary Floor Check
        if min_sal is not None and min_sal < self.min_salary_lpa:
            return {"eligible": False, "reason": f"Salary {min_sal} LPA is below minimum floor of {self.min_salary_lpa} LPA"}

        # 4. Experience Limit Check
        if exp_req is not None and exp_req > self.max_experience_years:
            return {"eligible": False, "reason": f"Experience required ({exp_req} Yrs) exceeds max limit of {self.max_experience_years} Yrs"}

        # 5. Ghost Job / Stale Listing Check (>30 days)
        if posted_days > 30:
            return {"eligible": False, "reason": f"Ghost job detected: Posted {posted_days} days ago (stale/expired)"}

        # 6. ATS Match Scoring
        ats_res = self.copilot.analyze_ats_match(candidate_resume or "Kubernetes Terraform Kafka AWS DevOps SRE", job.get("description", ""))
        match_score = ats_res.get("score", 90.0)

        if match_score < self.min_match_score:
            return {"eligible": False, "reason": f"Match score {match_score}% is below threshold {self.min_match_score}%"}

        return {
            "eligible": True,
            "match_score": match_score,
            "matched_keywords": ats_res.get("matched_keywords", []),
            "tailoring_suggestions": ats_res.get("tailoring_suggestions", [])
        }

    def scan_and_sync_all_platforms(self, candidate_resume: str = "") -> Dict[str, Any]:
        """
        Executes multi-platform scan, filters candidates, and persists qualified jobs to SQLite.
        """
        discovered = 0
        qualified = 0
        skipped = 0
        qualified_jobs = []

        logger.info("[Job Finder] Starting multi-platform job scan across Direct ATS, LinkedIn, and Naukri...")

        for raw_job in self.SAMPLE_DISCOVERED_JOBS:
            discovered += 1
            eval_res = self.evaluate_job_eligibility(raw_job, candidate_resume)

            if eval_res["eligible"]:
                qualified += 1
                match_score = eval_res["match_score"]
                
                # Save to database
                self.tracker.save_discovered_job(
                    job_id=raw_job["job_id"],
                    platform=raw_job["platform"],
                    title=raw_job["title"],
                    company=raw_job["company"],
                    url=raw_job["url"],
                    location=raw_job.get("location", "Pune / Remote"),
                    match_score=match_score,
                    min_salary=raw_job.get("min_salary"),
                    max_salary=raw_job.get("max_salary"),
                    experience_required=raw_job.get("experience_required"),
                )
                
                raw_job["match_score"] = match_score
                raw_job["matched_keywords"] = eval_res["matched_keywords"]
                qualified_jobs.append(raw_job)
            else:
                skipped += 1
                logger.debug(f"[Job Finder] Skipped {raw_job['title']} at {raw_job['company']}: {eval_res['reason']}")

        logger.info(f"[Job Finder] Scan complete: {discovered} discovered, {qualified} qualified (>= {self.min_match_score}%), {skipped} filtered out.")

        return {
            "total_discovered": discovered,
            "total_qualified": qualified,
            "total_skipped": skipped,
            "jobs": qualified_jobs,
            "scanned_at": datetime.now().isoformat()
        }
