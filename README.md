# JobPilot AI 🚀
Autonomous job search, application, and recruiter outreach engine for **Naukri** and **LinkedIn**.

---

## Key Features

1. **Intelligent Easy Apply Form Solver (LinkedIn)**:
   - **Numeric fields:** Strictly inputs digits only (e.g. `3`, never `3 years`).
   - **Yes/No questions:** Intelligently selects "Yes" or "No" radio buttons/dropdowns.
   - **Salary / CTC:** Inputs clean numbers without currency letters.
   - **Resume upload:** Directly attaches the updated `data/resume.pdf` during application.

2. **Naukri Master Profile Resume Sync & Quick Apply**:
   - `python main.py update-naukri-resume`: Uploads your latest `data/resume.pdf` to your master Naukri profile, boosting recruiter search visibility and ensuring 1-click Quick Apply sends the freshest resume.
   - 1-Click Quick Apply handler answering questionnaire popups automatically.

3. **HR Recruiter Cold Outreach via Gmail**:
   - Automatically detects HR emails in LinkedIn posts and job descriptions.
   - Drafts custom emails mentioning matching tech stack, notice period (e.g. immediate / 15-day release), and CTC.
   - Fallback cold application template when no job description is provided.
   - Direct Gmail sending (with `data/resume.pdf` attached) and duplicate prevention in SQLite.

4. **Resume Relevance Matcher**:
   - Parses `data/resume.pdf` using `pypdf`.
   - Computes relevance match scores (0.0 to 1.0) and skips internships, irrelevant sales roles, or out-of-range positions.

5. **Persistent Session Management**:
   - Saves cookies and session tokens in `data/browser_profile/`.
   - Log in once manually (`python main.py login`) with 2FA/OTP; future runs stay authenticated.

---

## Quick Reference CLI Commands

| Command | Description |
| :--- | :--- |
| `python main.py setup` | Interactive terminal wizard to configure your profile and search keywords |
| `python main.py test-config` | Review current candidate profile and search settings |
| `python main.py test-resume` | Test resume PDF extraction and job relevance match scoring |
| `python main.py test-email` | Preview generated HR email outreach draft |
| `python main.py login` | Launch browser to sign in to Naukri & LinkedIn once |
| `python main.py check-session` | Verify active login status on both platforms |
| `python main.py update-naukri-resume` | Upload updated `data/resume.pdf` to your Naukri master profile |
| `python main.py run-naukri` | Search and 1-click apply on Naukri |
| `python main.py run-linkedin` | Search and Easy Apply on LinkedIn (plus HR email outreach) |
| `python main.py run` | Run automated application across all enabled platforms |
| `python main.py status` | View today's application count vs daily limits |
| `python main.py history` | View recent application attempts and statuses |

---

## Gmail HR Outreach Configuration

To enable live email sending to HR contacts found in LinkedIn posts:
1. Generate a **Google App Password** (Google Account $\rightarrow$ Security $\rightarrow$ 2-Step Verification $\rightarrow$ App Passwords).
2. Set environment variables (or enter in terminal):
   ```powershell
   $env:GMAIL_ADDRESS="your.email@gmail.com"
   $env:GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
   ```
*(If no password is set, JobPilot AI automatically runs in safe **Simulation / Preview mode** so you can inspect emails without sending).*
