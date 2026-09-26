"""
Cover Letter Generator Engine — JobPlus AI Production
Generates tailored, human-sounding, punchy cover letters for direct company ATS, job boards, and freelance proposals.
Avoids generic AI clichés ("I hope this finds you well", "thrilled to apply", "esteemed organization").
"""

from typing import Dict, Any, Optional
import os
from datetime import datetime

class CoverLetterGenerator:
    """
    Generates tailored cover letters dynamically matching candidate profile
    and targeted company/position specifications.
    """

    TEMPLATES = {
        "devops_sre": """Dear {hiring_manager},

I am writing to express my strong interest in the {position} role at {company}. With over {experience_years} years of hands-on experience designing, deploying, and maintaining resilient cloud infrastructure across AWS and Azure, I specialize in automating CI/CD pipelines, container orchestration with Kubernetes, and managing Infrastructure as Code via Terraform.

At my current role as Digital Engineer at {current_company}, I have:
• Standardized Kubernetes clusters using ArgoCD and Helm charts, cutting deployment downtime by 40%.
• Authored modular Terraform codebases managing multi-region cloud networks, IAM policies, and VPC peering.
• Maintained high-throughput event streaming infrastructure with Apache Kafka, guaranteeing 99.95% system availability.
• Configured Prometheus, Grafana, and Alertmanager monitoring stacks for proactive anomaly detection.

{custom_pitch}

My notice period is currently {notice_period} (negotiable for an early release), and I am based in {location} with full flexibility for hybrid or remote arrangements.

I welcome the opportunity to discuss how my technical background in {core_skills} aligns with {company}'s engineering objectives.

Sincerely,
{candidate_name}
{contact_phone} | {contact_email}
{linkedin_url}
""",
        "kafka_admin": """Dear {hiring_manager},

I am reaching out regarding the {position} opportunity at {company}. Having spent the last {experience_years} years engineering distributed event-streaming platforms and production DevOps pipelines, I have deep domain expertise in Apache Kafka cluster sizing, partition tuning, Schema Registry, and KRaft/Zookeeper architectures.

Key highlights from my work at {current_company}:
• Scaled and monitored multi-broker Kafka clusters processing high-volume daily event streams with sub-second consumer latency.
• Automated Kafka broker provisioning and topic lifecycle management on Kubernetes using Strimzi and custom Helm deployments.
• Integrated centralized logging, distributed tracing, and real-time metric dashboards using Prometheus and Grafana.

I am particularly excited about {company}'s data engineering roadmap and would love to bring my operational discipline in event-driven architectures to your team. My official notice period is {notice_period}, and I am available to join promptly.

Best regards,
{candidate_name}
{contact_phone} | {contact_email}
""",
        "freelance_proposal": """Hi {client_name},

I saw your project regarding {position} / cloud infrastructure requirement. I am a Senior DevOps & Cloud Infrastructure Engineer with {experience_years}+ years of experience specializing in {core_skills}.

How I can deliver this for you:
1. Architecture & IaC: Clean, modular Terraform scripts for automated, repeatable cloud provisioning on AWS/Azure.
2. Containerization: Dockerizing applications and setting up resilient Kubernetes (EKS/AKS) or ECS environments.
3. CI/CD Pipeline: Complete end-to-end automated deployment workflows (GitHub Actions / GitLab CI) with automated linting and security scanning.
4. Monitoring & Telemetry: Turnkey Grafana and Prometheus monitoring setup with alert triggers.

I can deliver an initial milestone within 48 to 72 hours and provide clear documentation for handoff. Let's connect for 10 minutes to discuss your timeline and milestones.

Best regards,
{candidate_name}
Portfolio / Code: {linkedin_url}
"""
    }

    @classmethod
    def generate(
        cls,
        candidate_data: Dict[str, Any],
        company: str,
        position: str,
        template_type: str = "devops_sre",
        hiring_manager: str = "Hiring Team",
        custom_pitch: Optional[str] = None
    ) -> str:
        """
        Builds a customized cover letter for a given position and company.
        """
        template = cls.TEMPLATES.get(template_type, cls.TEMPLATES["devops_sre"])
        
        skills_str = ", ".join(candidate_data.get("skills", ["Kubernetes", "Terraform", "AWS", "Docker", "Kafka"]))
        
        if not custom_pitch:
            custom_pitch = f"Having researched {company}'s tech footprint, I am confident my hands-on background with scalable infrastructure and continuous delivery will deliver immediate value to your engineering sprints."

        letter = template.format(
            candidate_name=candidate_data.get("name", "Rajesh Madhukar Saindane"),
            current_company=candidate_data.get("current_company", "DGLiger Consulting"),
            experience_years=candidate_data.get("experience_years", "5.0"),
            notice_period=candidate_data.get("notice_period", "30 Days"),
            location=candidate_data.get("location", "Pune, India"),
            contact_phone=candidate_data.get("phone", "+91 8830807939"),
            contact_email=candidate_data.get("email", "rajeshsaindane264@gmail.com"),
            linkedin_url=candidate_data.get("linkedin_url", "https://linkedin.com/in/rajesh-saindane"),
            company=company,
            position=position,
            hiring_manager=hiring_manager,
            client_name=hiring_manager,
            core_skills=skills_str,
            custom_pitch=custom_pitch
        )
        return letter

    @classmethod
    def save_to_file(cls, text: str, output_path: str) -> str:
        """Saves generated cover letter to disk."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        return output_path
