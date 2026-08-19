<!--
Onboarding email template.

Merge fields:
- {{client.contact_name}}        — Client contact first name
- {{agency.name}}                — Agency name (e.g., "WEBRIS")
- {{agency.email}}               — Agency contact email
- {{agency.website}}             — Agency website URL
- {{owner.name}}                 — Owner's full name
- {{owner.title}}                — Owner's title (e.g., "Managing Partner")
- {{drive_folder_link}}          — Client folder URL (omit section if missing)
- {{assets_folder_link}}         — Client Assets subfolder URL (omit if missing)
- {{access_checklist_link}}      — Access-instructions doc URL (defaults to the standard access doc; omit section only if explicitly unavailable)
- {{scheduling_link}}            — Booking link. Resolve owner.calendar_link FIRST, then agency.calendar_link. Confirm with user before drafting.
- {{primary_color}}              — Brand primary color, falls back to #2563eb
- {{secondary_color}}            — Brand secondary color, falls back to #1e40af

Formatting requirements:
- All body text MUST render at a uniform 16px font size.
- No h1/h2 visual hierarchy. Section headers are bolded inline only.
- No "Welcome to {{agency.name}}!" salutation. Open with a simple "Hi {{contact_name}}," then body.
- Opening line MUST read exactly: "We're excited to kick off your campaign."
- Link color uses {{primary_color}} (with fallback). No CTA buttons with backgrounds — keep links inline.
-->

Subject: {{agency.name}} — Let's Get Started!

<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #1f2937; max-width: 640px; margin: 0 auto; padding: 24px; background: #ffffff;">

  <p style="font-size: 16px;">Hi {{client.contact_name}},</p>

  <p style="font-size: 16px;">We're excited to kick off your campaign. Our team has already started getting things set up on our end — here's what you'll need to do over the next few days so we can hit the ground running.</p>

  <p style="font-size: 16px;"><strong>Your client workspace</strong></p>
  <p style="font-size: 16px;">We've set up a shared Google Drive folder where all your project documents, deliverables, and assets will live:</p>
  <ul style="font-size: 16px;">
    <li><a href="{{drive_folder_link}}" style="color: {{primary_color}};">{{client.company_name}} — Client Folder</a></li>
    <li><a href="{{assets_folder_link}}" style="color: {{primary_color}};">Client Assets (upload logos, brand files, etc. here)</a></li>
  </ul>

  <p style="font-size: 16px;"><strong>Step 1 — Grant us access</strong></p>
  <p style="font-size: 16px;">To begin work, we'll need access to your Google Analytics 4, Google Search Console, your CMS, and Google Business Profile. Here is a link to <a href="{{access_checklist_link}}" style="color: {{primary_color}};">a document with details on how to get us access</a>. If it's too much to handle or you need help, we'll walk through it together on the kickoff call.</p>

  <p style="font-size: 16px;"><strong>Step 2 — Book your kickoff call</strong></p>
  <p style="font-size: 16px;">Once you've started on the access checklist, grab a slot on my calendar so we can walk through your goals, priorities, and timeline:</p>
  <p style="font-size: 16px;"><a href="{{scheduling_link}}" style="color: {{primary_color}};">Schedule Kickoff Call</a></p>

  <p style="font-size: 16px;"><strong>What happens next</strong></p>
  <ol style="font-size: 16px;">
    <li>Days 1–3: You complete the access checklist; we begin the website quality audit.</li>
    <li>Day 3: Kickoff call to align on strategy.</li>
    <li>Week 2: We deliver your project timeline and Sprint 1 begins.</li>
  </ol>

  <p style="font-size: 16px;">If anything is unclear or you have questions, just reply to this email — I'm your point of contact throughout the engagement.</p>

  <p style="font-size: 16px;">Looking forward to working together,</p>

  <p style="font-size: 16px;">{{owner.name}}<br>{{owner.title}}, {{agency.name}}<br><a href="mailto:{{agency.email}}" style="color: {{primary_color}};">{{agency.email}}</a> · <a href="{{agency.website}}" style="color: {{primary_color}};">{{agency.website}}</a></p>

</body>
</html>

<!--
Conditional rendering notes:
- If {{drive_folder_link}} is empty, omit the "Your client workspace" block entirely.
- {{access_checklist_link}} defaults to the standard access-instructions doc; only omit Step 1 if explicitly unavailable.
- {{scheduling_link}} resolves owner.calendar_link first, then agency.calendar_link; omit Step 2 only if neither exists.
- If branding colors are missing on agency profile, use defaults: primary_color = #2563eb, secondary_color = #1e40af.
-->
