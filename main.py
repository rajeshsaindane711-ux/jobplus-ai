import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import load_profile, load_search_config
from src.database import DatabaseTracker
from src.utils.logger import logger

console = Console(safe_box=True)

def display_banner():
    banner = """
   ================================================
           J O B P I L O T   A I  [v1.0]
     Autonomous Job Search & Application Engine
   ================================================
    """
    console.print(Panel(banner.strip(), style="bold cyan", expand=False))

def cmd_test_config(args):
    """Validates configuration files and prints profile summary."""
    try:
        profile = load_profile()
        search_config = load_search_config()

        console.print("[bold green]✓ Configurations loaded successfully![/bold green]\n")

        table = Table(title="Candidate Profile Summary", show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Full Name", f"{profile.candidate.first_name} {profile.candidate.last_name}")
        table.add_row("Email", profile.candidate.email)
        table.add_row("Phone", f"{profile.candidate.phone_country_code} {profile.candidate.phone}")
        table.add_row("Current Role", profile.experience.current_job_title)
        table.add_row("Total Experience", f"{profile.experience.total_years} years")
        table.add_row("Notice Period", f"{profile.experience.notice_period_days} days")
        table.add_row("Current / Expected CTC", f"{profile.experience.current_ctc_lakhs} LPA / {profile.experience.expected_ctc_lakhs} LPA")
        console.print(table)

        search_table = Table(title="Search Criteria", show_header=True, header_style="bold green")
        search_table.add_column("Parameter", style="cyan")
        search_table.add_column("Configured Value", style="white")
        search_table.add_row("Target Roles", ", ".join(search_config.search.keywords))
        search_table.add_row("Locations", ", ".join(search_config.search.locations))
        search_table.add_row("Experience Range", f"{search_config.search.experience_min_years} - {search_config.search.experience_max_years} years")
        search_table.add_row("Naukri Daily Limit", str(search_config.platforms.get("naukri", {}).daily_limit))
        search_table.add_row("LinkedIn Daily Limit", str(search_config.platforms.get("linkedin", {}).daily_limit))
        console.print(search_table)

    except Exception as e:
        console.print(f"[bold red]Configuration error: {e}[/bold red]")
        sys.exit(1)

def cmd_status(args):
    """Displays application statistics from local SQLite database."""
    tracker = DatabaseTracker()
    stats = tracker.get_summary_stats()

    naukri_today = tracker.get_today_applied_count("naukri")
    linkedin_today = tracker.get_today_applied_count("linkedin")

    console.print(Panel(
        f"[bold cyan]Today's Applications:[/bold cyan]\n"
        f" • [yellow]Naukri:[/yellow] {naukri_today} applied\n"
        f" • [blue]LinkedIn:[/blue] {linkedin_today} applied",
        title="Daily Quotas & Activity",
        border_style="cyan"
    ))

    table = Table(title="All-Time Application Stats", show_header=True, header_style="bold blue")
    table.add_column("Platform", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Count", style="green")

    if not stats:
        console.print("[dim]No applications recorded yet in database.[/dim]\n")
        return

    for platform, status_counts in stats.items():
        for status, count in status_counts.items():
            table.add_row(platform.title(), status.title(), str(count))

    console.print(table)

def cmd_history(args):
    """Shows the most recent application attempts."""
    tracker = DatabaseTracker()
    history = tracker.get_recent_applications(limit=args.limit)

    if not history:
        console.print("[dim]No application history found.[/dim]\n")
        return

    table = Table(title=f"Last {len(history)} Application Events", show_header=True, header_style="bold yellow")
    table.add_column("Date/Time", style="dim")
    table.add_column("Platform", style="cyan")
    table.add_column("Company", style="white")
    table.add_column("Title", style="green")
    table.add_column("Status", style="magenta")

    for h in history:
        table.add_row(
            str(h["applied_at"])[:16],
            h["platform"].title(),
            h["company"],
            h["title"],
            h["status"].title(),
        )
    console.print(table)

def cmd_setup(args):
    """Interactive wizard to easily configure candidate profile and search preferences."""
    import yaml
    from src.config import CONFIG_DIR, load_profile, load_search_config

    console.print("\n[bold cyan]═══════════════════ JobPilot AI Configuration Wizard ═══════════════════[/bold cyan]")
    console.print("[dim]Press Enter to keep the current/default value shown in [brackets].[/dim]\n")

    profile = load_profile()
    search_cfg = load_search_config()

    def prompt(label: str, default: str) -> str:
        res = console.input(f"[bold white]{label}[/bold white] [[cyan]{default}[/cyan]]: ").strip()
        return res if res else default

    # Candidate Profile
    console.print("[bold yellow]1. Candidate Information[/bold yellow]")
    profile.candidate.first_name = prompt("First Name", profile.candidate.first_name)
    profile.candidate.last_name = prompt("Last Name", profile.candidate.last_name)
    profile.candidate.email = prompt("Email Address", profile.candidate.email)
    profile.candidate.phone = prompt("Phone Number (10 digits)", profile.candidate.phone)
    profile.candidate.current_location = prompt("Current City", profile.candidate.current_location or "Bengaluru, India")

    # Experience & CTC
    console.print("\n[bold yellow]2. Experience & Salary Details[/bold yellow]")
    profile.experience.current_job_title = prompt("Current Job Title / Designation", profile.experience.current_job_title)
    profile.experience.current_company = prompt("Current Company", profile.experience.current_company)
    profile.experience.total_years = float(prompt("Total Years of Experience", str(profile.experience.total_years)))
    profile.experience.notice_period_days = int(prompt("Notice Period in Days (e.g. 0, 15, 30, 60)", str(profile.experience.notice_period_days)))
    profile.experience.current_ctc_lakhs = float(prompt("Current CTC in LPA (Lakhs)", str(profile.experience.current_ctc_lakhs)))
    profile.experience.expected_ctc_lakhs = float(prompt("Expected CTC in LPA (Lakhs)", str(profile.experience.expected_ctc_lakhs)))

    # Search Criteria
    console.print("\n[bold yellow]3. Search & Target Preferences[/bold yellow]")
    curr_roles = ", ".join(search_cfg.search.keywords)
    new_roles = prompt("Target Job Roles (comma-separated)", curr_roles)
    search_cfg.search.keywords = [r.strip() for r in new_roles.split(",") if r.strip()]

    curr_locs = ", ".join(search_cfg.search.locations)
    new_locs = prompt("Target Locations (comma-separated)", curr_locs)
    search_cfg.search.locations = [l.strip() for l in new_locs.split(",") if l.strip()]

    # Save to files
    profile_path = CONFIG_DIR / "profile.yaml"
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(profile.model_dump(), f, default_flow_style=False, sort_keys=False)

    search_path = CONFIG_DIR / "search_config.yaml"
    with open(search_path, "w", encoding="utf-8") as f:
        yaml.dump(search_cfg.model_dump(), f, default_flow_style=False, sort_keys=False)

    console.print("\n[bold green]✓ Configuration successfully updated and saved![/bold green]")
    console.print("[dim]Run 'python main.py test-config' to review your updated settings.[/dim]\n")

def cmd_login(args):
    """Launches interactive browser for manual login to Naukri and LinkedIn."""
    from src.browser import BrowserManager
    browser = BrowserManager(headless=False)
    browser.launch_interactive_login()

def cmd_check_session(args):
    """Checks whether saved sessions are authenticated."""
    from src.browser import BrowserManager
    browser = BrowserManager(headless=True)
    console.print("[cyan]Checking authenticated sessions...[/cyan]")
    status = browser.check_login_status()

    table = Table(title="Authentication Status", show_header=True, header_style="bold green")
    table.add_column("Platform", style="cyan")
    table.add_column("Status", style="white")

    for platform, is_logged_in in status.items():
        state_str = "[bold green]✓ Logged In[/bold green]" if is_logged_in else "[bold red]✗ Not Logged In[/bold red]"
        table.add_row(platform.title(), state_str)

    console.print(table)
    if not all(status.values()):
        console.print("[yellow]Tip: Run 'python main.py login' to log into unauthenticated platforms.[/yellow]\n")

def cmd_test_resume(args):
    """Tests resume extraction and match scoring."""
    from src.utils.resume_matcher import ResumeMatcher
    profile = load_profile()
    search_config = load_search_config()

    resume_path = Path(profile.resume_path)
    if not resume_path.exists():
        console.print(f"[yellow]Notice: No resume found at '{resume_path}'. Place your resume at 'data/resume.pdf' for auto-extraction.[/yellow]")

    matcher = ResumeMatcher(resume_path if resume_path.exists() else None)
    console.print(f"[cyan]Detected skills from resume/profile:[/cyan] {', '.join(sorted(matcher.detected_skills)) or 'None (add resume or skills in profile.yaml)'}")

    # Test match score against sample jobs
    test_jobs = [
        "Senior Python Developer (Django, FastAPI, AWS)",
        "Full Stack Web Developer (React, Node.js)",
        "Sales & Business Development Representative",
        "Junior Python Intern",
    ]

    table = Table(title="Sample Job Relevance Match Scores", show_header=True, header_style="bold yellow")
    table.add_column("Sample Job Title", style="white")
    table.add_column("Match Score", style="cyan")
    table.add_column("Decision", style="magenta")

    for job in test_jobs:
        score = matcher.calculate_match_score(
            job_title=job,
            candidate_skills=list(matcher.detected_skills),
            target_roles=search_config.search.keywords,
        )
        decision = "[bold green]APPLY[/bold green]" if score >= 0.3 else "[dim red]SKIP[/dim red]"
        table.add_row(job, f"{score:.2f}", decision)

    console.print(table)

def cmd_update_naukri_resume(args):
    """Uploads updated resume PDF to Naukri profile."""
    from src.browser import BrowserManager
    from src.platforms.naukri import NaukriAutomator

    profile = load_profile()
    search_cfg = load_search_config()
    tracker = DatabaseTracker()

    browser = BrowserManager(headless=search_cfg.safety.headless)
    page = browser.new_page()

    automator = NaukriAutomator(
        page=page,
        profile=profile,
        platform_config=search_cfg.platforms.get("naukri"),
        safety_config=search_cfg.safety,
        tracker=tracker,
    )

    console.print("[cyan]Checking Naukri login status...[/cyan]")
    if not automator.is_logged_in():
        console.print("[bold red]Error: You are not logged into Naukri. Run 'python main.py login' first.[/bold red]")
        browser.close()
        return

    success = automator.update_profile_resume()
    browser.close()
    if success:
        console.print("[bold green]✓ Naukri profile resume updated successfully![/bold green]")
    else:
        console.print("[bold red]✗ Failed to update Naukri resume.[/bold red]")

def cmd_run_naukri(args):
    """Executes Naukri job search and 1-click apply."""
    from src.browser import BrowserManager
    from src.platforms.naukri import NaukriAutomator

    profile = load_profile()
    search_cfg = load_search_config()
    tracker = DatabaseTracker()

    browser = BrowserManager(headless=search_cfg.safety.headless)
    page = browser.new_page()

    automator = NaukriAutomator(
        page=page,
        profile=profile,
        platform_config=search_cfg.platforms.get("naukri"),
        safety_config=search_cfg.safety,
        tracker=tracker,
    )

    console.print("[cyan]Verifying Naukri session...[/cyan]")
    if not automator.is_logged_in():
        console.print("[bold red]Error: Not logged into Naukri. Run 'python main.py login' first.[/bold red]")
        browser.close()
        return

    for kw in search_cfg.search.keywords:
        for loc in search_cfg.search.locations:
            console.print(f"\n[bold yellow]Searching Naukri for '{kw}' in '{loc}'...[/bold yellow]")
            results = automator.search_and_apply(kw, loc)
            console.print(f"[green]Batch results: {results}[/green]")

    browser.close()

def cmd_run_linkedin(args):
    """Executes LinkedIn Easy Apply search and auto-apply."""
    from src.browser import BrowserManager
    from src.platforms.linkedin import LinkedInAutomator

    profile = load_profile()
    search_cfg = load_search_config()
    tracker = DatabaseTracker()

    browser = BrowserManager(headless=search_cfg.safety.headless)
    page = browser.new_page()

    automator = LinkedInAutomator(
        page=page,
        profile=profile,
        platform_config=search_cfg.platforms.get("linkedin"),
        safety_config=search_cfg.safety,
        tracker=tracker,
    )

    console.print("[cyan]Verifying LinkedIn session...[/cyan]")
    if not automator.is_logged_in():
        console.print("[bold red]Error: Not logged into LinkedIn. Run 'python main.py login' first.[/bold red]")
        browser.close()
        return

    for kw in search_cfg.search.keywords:
        for loc in search_cfg.search.locations:
            console.print(f"\n[bold yellow]Searching LinkedIn Easy Apply for '{kw}' in '{loc}'...[/bold yellow]")
            results = automator.search_and_apply(kw, loc)
            console.print(f"[green]Batch results: {results}[/green]")

    browser.close()

def cmd_test_email(args):
    """Tests HR email drafting with sample job details."""
    from src.platforms.email_outreach import EmailOutreachEngine
    profile = load_profile()
    tracker = DatabaseTracker()
    engine = EmailOutreachEngine(profile, tracker)

    console.print("\n[bold cyan]Testing HR Email Auto-Drafter (Simulation Mode)[/bold cyan]")
    engine.send_email(
        to_email="recruiter@example.com",
        job_title="Senior Python / Backend Developer",
        company="Global Tech Labs",
        job_description="Looking for an immediate or 15-day notice Python engineer with FastAPI, AWS, and Microservices experience.",
    )

def cmd_run_all(args):
    """Runs automated applications on all enabled platforms."""
    search_cfg = load_search_config()
    if search_cfg.platforms.get("naukri", {}).enabled:
        cmd_run_naukri(args)
    if search_cfg.platforms.get("linkedin", {}).enabled:
        cmd_run_linkedin(args)

def main():
    display_banner()
    parser = argparse.ArgumentParser(description="JobPilot AI - Autonomous Job Application Engine")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # setup
    subparsers.add_parser("setup", help="Interactive wizard to update candidate profile & search preferences")

    # test-config
    subparsers.add_parser("test-config", help="Validate YAML profile and search settings")

    # test-resume
    subparsers.add_parser("test-resume", help="Test resume parsing and auto-match scoring")

    # test-email
    subparsers.add_parser("test-email", help="Preview generated HR email outreach draft")

    # update-naukri-resume
    subparsers.add_parser("update-naukri-resume", help="Upload updated resume to Naukri master profile")

    # login
    subparsers.add_parser("login", help="Launch interactive browser to log in to Naukri & LinkedIn")

    # check-session
    subparsers.add_parser("check-session", help="Check if saved browser sessions are logged in")

    # run-naukri
    subparsers.add_parser("run-naukri", help="Search and auto-apply on Naukri")

    # run-linkedin
    subparsers.add_parser("run-linkedin", help="Search and auto-apply on LinkedIn Easy Apply")

    # run
    subparsers.add_parser("run", help="Run automated apply across all enabled platforms")

    # status
    subparsers.add_parser("status", help="Show application counts and daily quotas")

    # history
    history_parser = subparsers.add_parser("history", help="List recent application history")
    history_parser.add_argument("--limit", type=int, default=15, help="Number of records to show")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "test-config":
        cmd_test_config(args)
    elif args.command == "test-resume":
        cmd_test_resume(args)
    elif args.command == "test-email":
        cmd_test_email(args)
    elif args.command == "update-naukri-resume":
        cmd_update_naukri_resume(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "check-session":
        cmd_check_session(args)
    elif args.command == "run-naukri":
        cmd_run_naukri(args)
    elif args.command == "run-linkedin":
        cmd_run_linkedin(args)
    elif args.command == "run":
        cmd_run_all(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "history":
        cmd_history(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
