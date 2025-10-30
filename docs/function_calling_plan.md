# Implementation Plan: Function-Calling System with Attachments

## Overview
Implement a full function-calling system that allows the LLM to generate attachments (calendar files, CSV exports, etc.) in email responses.

## Phase 1: Architecture & Design

### 1.1 Tool System Design
- **Tool Registry**: Central registry of available tools
- **Tool Schema**: Each tool has:
  - Name and description
  - Input parameters (with types and descriptions)
  - Output format specification
  - Execution function

### 1.2 Tool Categories
- **Calendar Tools**:
  - `create_calendar_event`: Generate .ics file for single event
  - `create_calendar_from_data`: Generate .ics with multiple events from CSV/structured data

- **Export Tools**:
  - `export_to_csv`: Export data to CSV format
  - `create_text_file`: Generate formatted text file
  - `create_json_file`: Export structured data as JSON

- **Future Tools** (optional):
  - `create_pdf`: Generate PDF documents
  - `create_chart`: Generate charts/graphs as images

## Phase 2: Core Implementation

### 2.1 Create Tool System (`src/rag/tools/`)
```
src/rag/tools/
├── __init__.py
├── base.py           # Base tool class and registry
├── calendar_tools.py # ICS generation tools
├── export_tools.py   # CSV, JSON, text export tools
└── tool_executor.py  # Tool execution engine
```

**Files to create**:
1. `base.py`: Tool base class, registry, schema definitions
2. `calendar_tools.py`: Functions to create .ics files
3. `export_tools.py`: Functions to export data
4. `tool_executor.py`: Executes tools and handles results

### 2.2 Update RAG Engine (`src/rag/rag_engine.py`)
- Add function calling support using OpenAI's native function calling
- Parse LLM responses for tool calls
- Execute requested tools
- Include tool results in final response

### 2.3 Update Query Handler (`src/rag/query_handler.py`)
- Accept tool outputs from RAG engine
- Convert tool outputs to email attachments
- Pass attachments to email sender

### 2.4 Update Email Processor (`src/email/email_processor.py`)
- Receive attachments from query handler
- Pass them to email sender's `send_reply()` method

## Phase 3: Tool Implementations

### 3.1 Calendar Tool Implementation
```python
def create_calendar_event(
    title: str,
    start_date: str,      # ISO format
    end_date: str,        # ISO format
    description: str = "",
    location: str = ""
) -> dict:
    """Generate .ics calendar file"""
    # Returns: {'content': ics_content, 'filename': 'event.ics', 'content_type': 'text/calendar'}
```

### 3.2 CSV Export Tool
```python
def export_to_csv(
    data: List[dict],
    filename: str = "export.csv"
) -> dict:
    """Export data to CSV format"""
    # Returns: {'content': csv_content, 'filename': filename, 'content_type': 'text/csv'}
```

## Phase 4: System Integration

### 4.1 Data Flow
```
User Query
    ↓
RAG Engine (with function calling)
    ↓
LLM Response + Tool Calls
    ↓
Tool Executor
    ↓
Tool Results (attachments)
    ↓
Query Handler
    ↓
Email Processor
    ↓
Email Sender (with attachments)
    ↓
User receives email with attachments
```

### 4.2 System Prompt Updates
Add to LLM system prompt:
```
Available Tools:
1. create_calendar_event - Generate .ics calendar file
2. export_to_csv - Export data to CSV
3. create_text_file - Create formatted text file

When user requests a calendar invite or data export, use these tools.
```

## Phase 5: Testing & Validation

### 5.1 Unit Tests
- Test each tool function independently
- Test tool registry and schema validation
- Test tool executor error handling

### 5.2 Integration Tests
- Test end-to-end: query → tool call → attachment generation → email sending
- Test multiple attachments in one email
- Test error scenarios (invalid parameters, tool failures)

### 5.3 Real-World Tests
- Create calendar event from natural language
- Export CSV data from KB query results
- Test attachment file formats and compatibility

## Phase 6: Documentation & Deployment

### 6.1 Documentation
- Tool usage guide for users
- Developer documentation for adding new tools
- Update README with attachment capabilities

### 6.2 Deployment
- Rebuild Docker image with new dependencies (if any)
- Test in Docker container
- Monitor logs for tool usage and errors

---

## Estimated Effort

- **Phase 1** (Design): 30 minutes
- **Phase 2** (Core): 1-2 hours
- **Phase 3** (Tools): 1 hour
- **Phase 4** (Integration): 1 hour
- **Phase 5** (Testing): 1 hour
- **Phase 6** (Docs): 30 minutes

**Total**: ~4-5 hours of development

## Dependencies

- `icalendar>=5.0.0` - For .ics calendar file generation
- Python standard library (csv, json, datetime)

## Success Criteria

1. User can request calendar event via natural language query
2. System generates valid .ics file and attaches to email
3. Calendar file opens correctly in calendar applications
4. System can export structured data to CSV
5. All changes work in Docker container
6. Comprehensive test coverage
