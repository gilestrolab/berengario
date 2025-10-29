# Email Authentication Issue - Diagnosis Report

**Date**: 2025-10-29
**Account**: dolsbot@ic.ac.uk
**Issue**: IMAP authentication fails despite correct credentials

---

## ✅ Confirmed Working

- ✓ Web login to Office 365 works with credentials
- ✓ No 2FA/MFA required
- ✓ IMAP server is reachable (outlook.office365.com:993)
- ✓ Server advertises AUTH=PLAIN support
- ✓ Network connectivity is fine

## ❌ The Problem

**Basic Authentication is DISABLED at the policy level for IMAP/POP protocols.**

Despite the server advertising `AUTH=PLAIN`, Imperial College has disabled basic authentication for IMAP/POP as a security measure. Web login works because it uses OAuth2, not basic authentication.

This is confirmed by:
- Server responds with "LOGIN failed" despite correct credentials
- Server advertises AUTH=PLAIN but rejects LOGIN commands
- Web login works (uses OAuth2) but IMAP login fails (uses basic auth)

---

## 🔧 Solutions (Choose One)

### Option 1: Enable IMAP Basic Auth (Recommended - Fastest)

**You need admin access to Office 365 or contact IT support.**

#### For User-Level Settings:
1. Log into **Microsoft 365 Admin Center**
2. Go to: **Users** → **Active users** → **dolsbot@ic.ac.uk**
3. Click **Mail** → **Manage email apps**
4. Ensure **"Authenticated SMTP"** and **"IMAP"** are checked
5. Save changes

#### For Tenant-Level Policy:
1. Go to **Exchange Admin Center**
2. Navigate to: **Settings** → **Authentication policies**
3. Check if IMAP basic auth is blocked
4. Create/modify policy to allow basic auth for this account

### Option 2: Contact Imperial IT Support

**Email**: ict-servicedesk@imperial.ac.uk

**Request Template**:
```
Subject: Enable IMAP Basic Authentication for dolsbot@ic.ac.uk

Hello,

I'm setting up automated email processing for the DoLS department and need
IMAP access enabled for the dolsbot@ic.ac.uk account.

Current issue:
- Web login works fine
- IMAP authentication fails with "LOGIN failed"
- The account needs to:
  - Accept IMAP connections
  - Allow basic authentication for IMAP

Could you please enable IMAP basic authentication for dolsbot@ic.ac.uk?

Alternatively, if basic auth is not allowed by policy, could you provide
guidance on configuring OAuth2 authentication for IMAP access?

Thank you,
Giorgio Gilestro
Department of Life Sciences
```

### Option 3: Implement OAuth2 Authentication

This requires code changes but is more secure:

**Pros:**
- More secure (no password in config)
- Complies with modern security policies
- Supported by Office 365

**Cons:**
- Requires code modifications
- More complex setup
- Needs app registration in Azure AD

If you want to go this route, let me know and I can implement OAuth2 support.

### Option 4: Test with Different Email Account

To verify the email processing code works while waiting for IT:

**Compatible email providers:**
- Gmail (with app-specific password if 2FA enabled)
- Yahoo Mail
- Personal email services
- Other Office 365 accounts with basic auth enabled

Just update `.env` with different IMAP credentials temporarily.

---

## 📝 Testing Scripts Created

### 1. `diagnose_email.py`
Interactive diagnostic tool with SSL/STARTTLS support:
```bash
python diagnose_email.py          # Interactive mode
python diagnose_email.py --quick  # Quick test with .env
```

### 2. `check_server_caps.py`
Check what authentication methods the server supports:
```bash
python check_server_caps.py
```

### 3. `test_auth_methods.py`
Detailed authentication testing and diagnosis:
```bash
python test_auth_methods.py
```

---

## 📊 Current Status

- ✅ Email processing code is complete and tested (149 tests passing)
- ✅ All components integrated and working
- ❌ Cannot test with production email due to authentication policy
- ⏳ Waiting for IMAP basic auth to be enabled OR
- ⏳ Waiting to implement OAuth2 authentication

---

## 🚀 Next Steps

1. **Contact Imperial IT** to enable IMAP basic auth (fastest solution)
2. **OR** Test with alternative email account to verify the code works
3. **OR** Let me implement OAuth2 authentication support

Choose which approach you'd like to take!
