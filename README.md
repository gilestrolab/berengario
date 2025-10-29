# RAGInbox

**A configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management.**

RAGInbox is a flexible infrastructure that combines document processing, vector search, and LLM-powered question answering with unique email integration capabilities. Deploy multiple instances with different configurations for various organizations or departments.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 📄 **Multi-format Document Processing**: PDF, DOCX, TXT, CSV support
- 🔍 **Semantic Search**: ChromaDB vector database for efficient retrieval
- 🤖 **LLM Integration**: OpenAI-compatible API support (OpenAI, Naga.ac, etc.)
- 📧 **Email Integration**: Automatic KB updates and query handling via email
- ⚙️ **Instance Configuration**: Deploy multiple customized instances
- 🔄 **Auto-monitoring**: Watch folders for automatic document updates
- 📊 **Source Citations**: All responses include source references

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/gilestrolab/RAGInbox.git
cd RAGInbox

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in editable mode
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and configure your instance:

```bash
# Instance Configuration (customize for your deployment)
INSTANCE_NAME=MyAssistant
INSTANCE_DESCRIPTION=AI assistant for my organization
ORGANIZATION=My Organization Name

# API Configuration
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1  # or https://api.naga.ac/v1
```

### Usage

```bash
# Process documents from Documents folder
raginbox --mode process

# Query the knowledge base
raginbox --mode query --query "What are the key policies?"

# Watch for new documents (runs continuously)
raginbox --mode watch
```

## Example Instances

### Example 1: Department Assistant (DoLS-GPT)

```env
INSTANCE_NAME=DoLS-GPT
INSTANCE_DESCRIPTION=AI assistant for the Department of Life Sciences
ORGANIZATION=Imperial College London
EMAIL_TARGET_ADDRESS=dols.gpt@imperial.ac.uk
```

### Example 2: HR Knowledge Base

```env
INSTANCE_NAME=HR-Assistant
INSTANCE_DESCRIPTION=Human Resources policy assistant
ORGANIZATION=Acme Corporation
EMAIL_TARGET_ADDRESS=hr.bot@acme.com
```

### Example 3: Technical Documentation

```env
INSTANCE_NAME=TechDocs-AI
INSTANCE_DESCRIPTION=Technical documentation assistant
ORGANIZATION=Tech Startup Inc
EMAIL_TARGET_ADDRESS=docs@techstartup.io
```

## Architecture

### Core Components

1. **Document Processing** (`src/document_processing/`)
   - Multi-format parser (PDF, DOCX, TXT, CSV)
   - Intelligent chunking with overlap
   - File monitoring for auto-updates

2. **Knowledge Base** (`src/document_processing/kb_manager.py`)
   - ChromaDB vector storage
   - Deduplication via file hashing
   - Efficient semantic search

3. **RAG Engine** (`src/rag/`)
   - LlamaIndex query engine
   - Customizable prompts per instance
   - Source citation

4. **Email Integration** (Phase 2 - Coming Soon)
   - IMAP inbox monitoring
   - Auto KB updates from CC'd emails
   - Automated email responses

### Tech Stack

- **Python 3.11+**
- **LlamaIndex**: RAG framework
- **ChromaDB**: Vector database
- **FastAPI**: Web framework (Phase 4)
- **OpenAI-compatible APIs**: Naga.ac, OpenAI, etc.

## Configuration Options

### Instance Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `INSTANCE_NAME` | Name of your assistant | `DoLS-GPT` |
| `INSTANCE_DESCRIPTION` | Purpose description | `AI assistant for...` |
| `ORGANIZATION` | Organization name | `Imperial College` |

### API Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | API key for LLM/embeddings | Required |
| `OPENAI_API_BASE` | API endpoint URL | `https://api.openai.com/v1` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENROUTER_MODEL` | LLM model name | `gpt-4o` |

### Document Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCUMENTS_PATH` | Path to documents folder | `./Documents` |
| `CHUNK_SIZE` | Text chunk size | `1024` |
| `CHUNK_OVERLAP` | Chunk overlap | `200` |
| `TOP_K_RETRIEVAL` | Number of chunks to retrieve | `5` |

## Development

### Project Structure

```
RAGInbox/
├── src/
│   ├── config.py                  # Configuration management
│   ├── demo_phase1.py            # CLI interface
│   ├── document_processing/
│   │   ├── document_processor.py # Document parsing
│   │   ├── kb_manager.py         # Vector DB operations
│   │   └── file_watcher.py       # File monitoring
│   ├── rag/
│   │   ├── rag_engine.py         # Query engine
│   │   └── query_handler.py      # Query processing
│   ├── email/ (Phase 2)
│   └── api/ (Phase 4)
├── tests/                         # Unit tests
├── Documents/                     # Source documents
├── pyproject.toml                 # Package configuration
└── README.md                      # This file
```

### Running Tests

```bash
pytest tests/ -v
```

### Code Quality

```bash
# Format with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/
```

## Roadmap

- [x] **Phase 1**: Core RAG with document processing
- [ ] **Phase 2**: Email inbox integration
- [ ] **Phase 3**: Automated email responses
- [ ] **Phase 4**: Web frontend
- [ ] **Phase 5**: Docker deployment

## API Providers

RAGInbox works with OpenAI-compatible APIs:

- **[Naga.ac](https://naga.ac)**: Recommended - cheaper, same models
- **[OpenAI](https://openai.com)**: Original provider
- **[OpenRouter](https://openrouter.ai)**: Multi-provider access

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- 📖 [Documentation](https://github.com/gilestrolab/RAGInbox)
- 🐛 [Issue Tracker](https://github.com/gilestrolab/RAGInbox/issues)
- 💬 [Discussions](https://github.com/gilestrolab/RAGInbox/discussions)

## Credits

Developed by [Giorgio Gilestro](https://github.com/gilestrolab) for flexible, email-integrated RAG deployments.
