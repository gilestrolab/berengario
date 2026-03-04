# Email Processing Rules

**Last Updated**: 2025-10-29

## Overview

Berengario processes incoming emails differently based on how the bot email address appears in the recipient fields. This allows for two distinct workflows:

1. **Query Mode** - User asks a question and expects a reply
2. **KB Ingestion Mode** - User shares information to be added to the knowledge base

---

## Processing Logic

### Direct Emails (To: bot@example.com)

**When the bot is a direct recipient** (appears in the `To:` field):

**Regular emails**:
- ✉️ **Treated as**: Query
- 🤖 **Action**: Send automated reply using RAG
- 📝 **Content used**: Email body text
- 📎 **Attachments**: Not processed into KB
- 🔒 **Permission**: Query role required (configurable)

**Example scenarios**:
```
To: dolsbot@ic.ac.uk
From: alice@imperial.ac.uk
Subject: What is the vacation policy?

→ Bot replies with RAG-generated answer
```

**Forwarded emails** (configurable detection):
- ✉️ **Treated as**: KB contribution (NOT query)
- 🤖 **Action**: Add email body to knowledge base
- 📝 **Content used**: Email body + attachments
- 📎 **Attachments**: Processed if present
- 🔒 **Permission**: Teach role required

**Example scenarios**:
```
To: dolsbot@ic.ac.uk
From: alice@imperial.ac.uk
Subject: Fw: Important policy update

→ Email body added to KB (no reply sent)
```

**Configuration**:
- `FORWARD_TO_KB_ENABLED=true` - Enable forwarded email detection
- `FORWARD_SUBJECT_PREFIXES=fw,fwd` - Case-insensitive prefixes (customize for your language)

---

### CC/BCC/Forwarded Emails

**When the bot is CC'd, BCC'd, or forwarded to**:

- 📚 **Treated as**: Knowledge Base contribution
- 🤖 **Action**: Add to vector database (no reply sent)
- 📝 **Content used**: Email body + attachments
- 📎 **Attachments**: Processed and ingested
- 🔒 **Permission**: Teach role required

**Example scenarios**:

```
To: team@imperial.ac.uk
CC: dolsbot@ic.ac.uk
From: alice@imperial.ac.uk
Subject: Updated lab safety guidelines
Attachments: safety_policy_2025.pdf

→ Email body and PDF added to knowledge base
→ No reply sent
```

```
To: dolsbot@ic.ac.uk
From: alice@imperial.ac.uk
Subject: Fwd: Department meeting notes

→ Forwarded email added to knowledge base
→ No reply sent (because forwarded = CC'd)
```

---

### Teach Address Emails (Optional)

**When a dedicated teach address is configured** (`EMAIL_TEACH_ADDRESS`):

Emails addressed To: or CC: the teach address are **always** treated as KB ingestion, regardless of other routing rules. This takes highest priority in the decision tree.

- 📚 **Treated as**: Knowledge Base contribution
- 🤖 **Action**: Add to vector database (no reply sent)
- 📝 **Content used**: Email body + attachments
- 📎 **Attachments**: Processed and ingested
- 🔒 **Permission**: Teach role required

**Example scenarios**:
```
To: teach@berengar.io
From: alice@imperial.ac.uk
Subject: New vacation policy
Attachments: vacation_policy_2025.pdf

→ Email body and PDF added to knowledge base
→ No reply sent
```

**Configuration**:
- `EMAIL_TEACH_ADDRESS=teach@berengar.io` - Dedicated address for KB ingestion (optional)
- When not set, the main email address is used for both queries and teaching (via CC/forward)

---

## Decision Tree

```
┌─────────────────────────────────┐
│   Incoming Email Received       │
└────────────┬────────────────────┘
             │
             ▼
    ┌─────────────────────────────┐
    │ Teach address configured    │
    │ AND email addressed to it?  │
    └────┬──────────────┬─────────┘
         │ Yes          │ No
         ▼              ▼
  ┌──────────────┐  ┌────────────────────────┐
  │ Check TEACH  │  │ Check recipient field  │
  │  permission  │  └─────┬────────┬─────────┘
  └──┬───────┬───┘        │        │
     │Yes    │No     To: bot?   CC/BCC?
     ▼       ▼            │        │
  ┌────┐ ┌────┐           ▼        ▼
  │ KB │ │Rej.│   ┌──────────────┐  ┌────────────────────────┐
  │ING.│ └────┘   │ Forwarded?   │  │ Check TEACH permission │
  └────┘          │ (Fw:, Fwd:)  │  │ (TenantUser role)      │
                  └──┬────────┬──┘  └────┬───────────┬───────┘
                     │ Yes   │ No       │ Yes       │ No
                     ▼       ▼          ▼           ▼
               ┌──────────┐ ┌────────┐  │      ┌─────────┐
               │ Check    │ │ Check  │  │      │ Reject  │
               │ TEACH    │ │ QUERY  │  │      └─────────┘
               │permiss. │ │permiss. │  │
               └──┬───┬───┘ └─┬────┬─┘  │
                  │Yes│No    │Yes │No    ▼
                  ▼   ▼      ▼    ▼   ┌──────────────┐
               ┌────┐┌────┐┌────┐┌──┐│ KB INGESTION │
               │ KB ││Rej.││QRY ││Rj││    MODE      │
               │ING.││    ││MODE││  │└──────┬───────┘
               └────┘└────┘└──┬─┘└──┘       │
                              │              │
                              ▼              ▼
                       Send RAG reply  Add to vector DB
                                       (body + attachments)
```

**Key Points**:
- **Teach address takes highest priority**: If configured, emails to the teach address are always KB ingestion
- **Two separate permission checks**: Teach permission for KB ingestion, Query permission for queries
- **Hierarchical**: Admins and teachers can also query (parent validator pattern)
- **Forwarded emails** (To: bot) check teach permission, not query permission
- **CC/BCC emails** always check teach permission

---

## Access Control

### Role-Based Access Control

Berengario uses the **TenantUser** model with hierarchical roles to control access:

1. **Admin** role
   - Full permissions: can teach, query, and access admin panel
   - Can manage team members and system settings

2. **Member** role (with teach permission)
   - Can add content to the knowledge base via CC'd, BCC'd, and forwarded emails
   - Can also send queries and receive RAG replies

3. **Member** role (query only)
   - Can send direct questions and receive RAG replies
   - Cannot add content to the knowledge base

**Hierarchical Permissions**:
- **Admins** can do everything (teach + query + admin panel)
- **Members with teach** can teach and query
- **Members without teach** can only query

Users are managed via the admin panel or platform admin, not via flat files. Each user's permissions are stored in the `TenantUser` table in the database.

---

## Implementation Details

### Code Locations

**Decision logic**: `src/email/email_parser.py`
```python
def should_process_as_query(email: EmailMessage) -> bool:
    """Direct messages (To: bot) are queries."""
    return not email.is_cced

def should_process_for_kb(email: EmailMessage) -> bool:
    """CC'd/BCC'd/forwarded messages are KB contributions."""
    return email.is_authorized and email.is_cced
```

**Processing**: `src/email/email_processor.py`
```python
if parser.should_process_as_query(email):
    # Send RAG reply
    result = _process_query(email)
elif parser.should_process_for_kb(email):
    # Add to knowledge base
    result = _process_for_kb(email, mail_message)
```

### How CC Detection Works

The parser checks if the target bot address appears in the `To:` field:

```python
def is_cced_message(to_addresses: List[EmailAddress]) -> bool:
    """Check if target address is NOT in To: field."""
    target = self.target_address.lower()
    for addr in to_addresses:
        if addr.email.lower() == target:
            return False  # Direct recipient
    return True  # Must be CC/BCC/forwarded
```

**Note**: BCC recipients are indistinguishable from CC recipients from the bot's perspective, as BCC addresses don't appear in headers. The bot sees them both as "not in To: field".

---

## Use Cases

### 1. Department Q&A Bot

**Setup**:
```env
EMAIL_TARGET_ADDRESS=dolsbot@ic.ac.uk
INSTANCE_NAME=DoLS-GPT
```

**Workflow**:
- Staff email questions directly to `dolsbot@ic.ac.uk` → Get instant answers
- Admins CC `dolsbot@ic.ac.uk` on policy updates → Auto-added to KB

### 2. HR Knowledge Base

**Setup**:
```env
EMAIL_TARGET_ADDRESS=hr.assistant@company.com
INSTANCE_NAME=HR-Assistant
```

**Workflow**:
- Employees email `hr.assistant@company.com` with questions → Get policy answers
- HR team CCs `hr.assistant@company.com` on announcements → KB updated automatically

### 3. Technical Documentation Assistant

**Setup**:
```env
EMAIL_TARGET_ADDRESS=docs@techstartup.io
INSTANCE_NAME=TechDocs-AI
```

**Workflow**:
- Developers email `docs@techstartup.io` for API help → Get documentation snippets
- Engineering team CCs `docs@techstartup.io` on release notes → Documentation updated

---

## Migration Notes

### Previous Behavior (Before 2025-10-29)

- ❌ Direct emails (To: bot) → KB ingestion
- ❌ CC'd without attachments → Query
- ❌ CC'd with attachments → KB ingestion

### Current Behavior (After 2025-10-29)

- ✅ Direct emails (To: bot) → Query
- ✅ CC'd/BCC'd/forwarded → KB ingestion (regardless of attachments)

**Rationale**:
- More intuitive: "To: bot" implies expecting a direct response
- Simpler: No need to think about attachments when sharing information
- Clearer intent: User explicitly chooses query vs. KB contribution mode

---

## Testing

### Test Coverage

**Unit tests**: `tests/test_email_parser.py`
- `test_should_process_as_query_direct_message` ✓
- `test_should_process_as_query_cced_no_attachments` ✓
- `test_should_process_for_kb_authorized_direct` ✓
- `test_should_process_for_kb_cced_no_attachments` ✓

All 47 email parser tests passing ✓

### Manual Testing

**Test query mode**:
```bash
# Send email To: dolsbot@ic.ac.uk
# Subject: What is the refund policy?
# → Expect RAG reply
```

**Test KB ingestion**:
```bash
# Send email To: team@ic.ac.uk, CC: dolsbot@ic.ac.uk
# Attach: new_policy.pdf
# → Expect silent KB ingestion
```

---

## FAQ

**Q: What if I send to the bot AND CC others?**
A: If the bot appears in `To:`, it's treated as a query (unless it's a forwarded email). Other recipients are irrelevant.

**Q: Can I query the bot if I don't have an account?**
A: Only users with a TenantUser record and query permission can send queries. KB contributions require teach permission.

**Q: What happens to forwarded emails sent To: the bot?**
A: If forwarded detection is enabled (default), they're added to KB instead of triggering a reply. The subject is checked for prefixes like "Fw:" or "Fwd:".

**Q: Can I customize which languages' forwarding prefixes are detected?**
A: Yes! Set `FORWARD_SUBJECT_PREFIXES=fw,fwd,i,rv` for multi-language support (English: fw/fwd, Italian: i, Spanish: rv, etc.).

**Q: What is the teach address?**
A: An optional second email address (e.g., `teach@berengar.io`) dedicated to KB ingestion. Any email sent To: or CC: this address is always treated as teaching content, never as a query. Set it via `EMAIL_TEACH_ADDRESS` in `.env`.

**Q: Can the teach address be the same as the main address?**
A: No, that would make all direct emails become KB ingestion instead of queries. Use a different address, or rely on CC/forward for teaching.

**Q: Does the bot reply to CC'd emails?**
A: No. CC'd/BCC'd emails are silent KB ingestion with no reply.

**Q: Does the bot reply to forwarded emails?**
A: No. Forwarded emails (when detection is enabled) are treated as KB content, not queries.

**Q: What if I want to disable forwarded email detection?**
A: Set `FORWARD_TO_KB_ENABLED=false` in `.env`. Then forwarded emails To: bot will be treated as regular queries.

**Q: What if I want to add something to KB AND get a reply?**
A: Send two emails: one CC'd (or forwarded) for KB ingestion, one regular To: bot for the query.

**Q: Are attachments processed in query mode?**
A: Not currently. Attachments are only ingested from CC'd/BCC'd/forwarded emails.

**Q: What if there are no attachments in a forwarded email?**
A: The email body text is processed and added to the KB as a text document.

---

## Configuration Reference

**Environment Variables**:
```bash
# Email service
EMAIL_TARGET_ADDRESS=dolsbot@ic.ac.uk
EMAIL_CHECK_INTERVAL=300  # seconds

# Dedicated teach address (optional)
# EMAIL_TEACH_ADDRESS=teach@berengar.io  # Separate address for KB ingestion

# Forwarded email detection
FORWARD_TO_KB_ENABLED=true  # Treat forwarded emails as KB content
FORWARD_SUBJECT_PREFIXES=fw,fwd  # Customize for your language
```

**Access Control**:

Permissions are managed via the TenantUser table in the database, not via configuration files.
Users are added and assigned roles (admin, member) through the admin panel or platform admin.

**See also**:
- `.env.example` - Full configuration template
- `PLANNING.md` - System architecture
- `EMAIL_AUTH_ISSUE.md` - IMAP setup troubleshooting
