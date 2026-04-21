# Resume templates

Three templates, all strictly ATS-safe. The user picks one in Stage 6. All three follow the same structural rules — the differences are in typography and visual hierarchy.

## Hard ATS rules (all templates)

These rules apply to every template. Violations break ATS parsing.

1. **Single column.** No sidebars. No two-column layouts for skills-vs-experience. ATS parsers read left-to-right across the full width and two-column layouts cause titles to fuse with skills.
2. **Standard section headings only.** Allowed: `Summary`, `Professional Summary`, `Skills`, `Core Competencies`, `Experience`, `Professional Experience`, `Work Experience`, `Education`, `Certifications`, `Projects`, `Publications`, `Awards`. Not allowed: "My Journey", "What I Bring", "Where I've Been", "Impact."
3. **No tables, text boxes, or image placeholders.** Skills lists are inline, comma-separated or line-separated. No skill "bar" graphics, no percentage ratings.
4. **No headers or footers for critical info.** Contact info (name, email, phone, city, LinkedIn) goes in the main body at the top, not in a page header.
5. **Web-safe fonts.** Pick from: Arial, Calibri, Garamond, Georgia, Times New Roman. No custom Google Fonts, no brand fonts that require installation.
6. **Body 10-12pt, headings 14-16pt.** Section separators are standard horizontal lines or blank lines, not decorative elements.
7. **Standard bullets.** `•` or `-` only. No checkmarks, no arrows, no custom symbols.
8. **No icons, logos, graphics, or photos.** Not even a company logo next to an experience entry.
9. **Margins 0.5"-1".** Anything narrower crowds; anything wider wastes space.
10. **File naming.** `Resume - {Company} - {Role} - {YYYY-MM-DD}.docx` (and `.pdf`).

## Template 1: Clean Modern (default)

The safe default for 2026. Works for tech, marketing, ops, sales, product, design, and most non-specialized white-collar roles.

**Typography:**
- Calibri throughout
- Name: 18pt bold, centered or left-aligned
- Section headings: 14pt bold, small caps
- Body: 11pt
- Bullets: 11pt, hanging indent 0.25"

**Structure (top to bottom):**
1. **Name** (18pt bold)
2. **Contact line** (11pt): `City, State | email | phone | linkedin.com/in/handle | portfolio-url` (one line, pipe-separated)
3. **Summary** — 2-3 sentence role-tailored summary
4. **Skills** — 3 subsections: "Core Competencies", "Tools & Platforms", "Additional" (inline comma lists)
5. **Experience** — reverse chronological, company / title / location / dates, then bullets
6. **Education** — single line per entry (`Degree, Major | School | Year`)
7. **Certifications** (optional, single line each)

**Spacing:**
- 6pt after each heading
- 3pt between bullets
- 12pt before each new section

## Template 2: Harvard Classic

Traditional and serif. Signals formality. Choose for law, finance (traditional), consulting (traditional), academia, executive roles, and legal/government-adjacent positions.

**Typography:**
- Garamond throughout
- Name: 16pt bold, centered
- Section headings: 12pt bold underline, small caps
- Body: 11pt
- Bullets: 11pt, hanging indent 0.3"

**Structure:**
Same order as Clean Modern, but:
- Contact line is centered under name
- Section headings are centered and underlined
- Experience entries use tab-aligned dates (right-justified against right margin)
- Bullets use `•` glyph

**Spacing:**
- Slightly tighter: 4pt after headings, 2pt between bullets
- Feels more academic / formal

## Template 3: Mirror User

Inspects the user's uploaded resume and matches its typography + hierarchy. This is a compromise — the user might have a resume with some mildly non-standard choices (e.g., centered headings, a summary with a custom label). Mirror User keeps their flavor but SILENTLY FIXES any hard-ATS-violation patterns (two columns, icons, non-standard headings, tables).

**Process:**
1. Read the user's uploaded resume file (the newest one, as identified in Stage 1).
2. Extract: font family, body font size, heading font size, section heading style (bold / caps / underline / centered), bullet glyph, margin width.
3. Apply those choices to the tailored content, with hard-rule overrides:
   - If their original uses two columns → force single column.
   - If their original uses custom section labels → replace with standard ones but keep their style.
   - If their original uses icons → drop the icons.
   - If their original has a photo → drop the photo.
4. Warn the user after generating: "Your original resume used [X]. For ATS compatibility, I swapped it for [Y]. Let me know if that's a problem."

## The user's choice

Ask once in Stage 6, before generating any resume:

```
For your resume template, pick one:

**1. Clean Modern** — one-page, Calibri 11pt, contemporary. Good for tech/marketing/product/ops. (Default pick)
**2. Harvard Classic** — Garamond, centered headings, formal. Good for law, finance, consulting, academia, exec roles.
**3. Mirror Your Upload** — match the style of the resume you sent me. Great if you like your current design.
```

Store the pick in `fats-profile.json` as `resume_template`. Don't ask again in future sessions unless the user requests a change.

## Implementation

All three templates are implemented in `scripts/resume.py`. Each has two independent renderers — one for `.docx` (python-docx) and one for `.pdf` (reportlab direct). The public API dispatches on file extension:

```python
build_clean_modern(profile, tailored_content, "Resume.docx")  # → python-docx
build_clean_modern(profile, tailored_content, "Resume.pdf")   # → reportlab
build_resume("harvard", profile, tailored_content, "Resume.pdf")
build_mirror_user(profile, tailored_content, "Resume.pdf", source_docx_path=user_docx)
```

There is no `docx → pdf` conversion step. The PDF is generated directly, so output is identical across every platform — no MS Word, no LibreOffice, no Pango/cairo system libraries required. Call the rendering function twice per job (once with `.docx`, once with `.pdf`) to produce both outputs.

Fonts are bundled in `assets/fonts/`:

- **EB Garamond** (Regular + Bold) — serif, used for Harvard.
- **Carlito** (Regular + Bold) — metric-compatible Calibri substitute, used for Clean Modern.

Both are OFL-licensed. If the bundled TTFs are missing at runtime, PDF rendering falls back to ReportLab's built-in Times-Roman (for Garamond requests) or Helvetica (for Calibri requests) so nothing breaks — the output is just slightly less typographically faithful.
