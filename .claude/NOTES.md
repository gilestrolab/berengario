# Development Notes

## Testing Strategy
- **Always test code in the Docker container**, not with local `.venv`
- The `src/` directory is volume-mapped to the container, so code changes are immediately available
- Use `docker exec` to run tests and commands inside the container
- Container name: `raginbox-app-test`

## Embedding Model
- **Current Model**: text-embedding-3-large (3072 dimensions)
- **Provider**: Naga.ac (OpenAI-compatible API)
- **Cost**: $0.04/1M tokens (vs $0.13/1M from OpenAI)
- **Reason for upgrade**: Better handling of structured data (tables in PowerPoint)
- **Settings**:
  - Chunk size: 2048 (was 1024)
  - Chunk overlap: 400 (was 200)
  - TOP_K retrieval: 10 (was 5)

## Attachment Archival
- Email attachments are now permanently archived to `data/documents/` before cleanup
- Implemented in `attachment_handler.py::archive_attachments()`
- Called from `email_processor.py::_process_for_kb()` in the finally block
- Features:
  - Detects identical files by hash (no duplicates)
  - Adds timestamp suffix for different files with same name
  - Creates documents folder if it doesn't exist
