# Documentation

This directory contains all technical documentation for the DoLS-GPT / RAGInbox project.

## Core Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide for getting up and running
- **[DATA_STRUCTURE.md](DATA_STRUCTURE.md)** - Data directory structure, Docker volumes, backup strategies
- **[EMAIL_PROCESSING_RULES.md](EMAIL_PROCESSING_RULES.md)** - Email processing logic and decision tree
- **[DATABASE_DESIGN.md](DATABASE_DESIGN.md)** - Database abstraction layer design (SQLite/MariaDB)
- **[EMAIL_AUTH_ISSUE.md](EMAIL_AUTH_ISSUE.md)** - Office 365 authentication troubleshooting
- **[PHASE2_PLAN.md](PHASE2_PLAN.md)** - Phase 2 implementation plan and architecture

## Main Project Documentation

See the root directory for:
- **[../README.md](../README.md)** - Project overview, installation, and usage
- **[../PLANNING.md](../PLANNING.md)** - System architecture and design decisions
- **[../TASK.md](../TASK.md)** - Task tracking and implementation progress

## Documentation by Topic

### Setup & Configuration
- [QUICKSTART.md](QUICKSTART.md) - Getting started
- [DATA_STRUCTURE.md](DATA_STRUCTURE.md) - Data directory organization
- [../README.md](../README.md) - Installation and configuration

### Email Integration
- [EMAIL_PROCESSING_RULES.md](EMAIL_PROCESSING_RULES.md) - How emails are processed
- [EMAIL_AUTH_ISSUE.md](EMAIL_AUTH_ISSUE.md) - Authentication troubleshooting
- [PHASE2_PLAN.md](PHASE2_PLAN.md) - Email integration architecture

### Database & Storage
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Database design and migrations
- [DATA_STRUCTURE.md](DATA_STRUCTURE.md) - Storage structure and backup

### Architecture & Planning
- [../PLANNING.md](../PLANNING.md) - Overall system architecture
- [PHASE2_PLAN.md](PHASE2_PLAN.md) - Phase 2 detailed plan
- [../TASK.md](../TASK.md) - Implementation progress

## Contributing to Documentation

When adding new documentation:

1. **Create the file** in this `docs/` directory
2. **Update this README** with a link and description
3. **Use clear headers** and table of contents for long docs
4. **Include examples** and code snippets where appropriate
5. **Date your updates** (e.g., "Last Updated: 2025-10-29")
6. **Link to related docs** to help navigation

## Documentation Standards

- Use GitHub-flavored Markdown
- Include code examples in fenced code blocks with language tags
- Use relative links to reference other docs
- Keep docs focused on a single topic
- Update the "Last Updated" date when making changes
- Include a table of contents for docs longer than 100 lines
